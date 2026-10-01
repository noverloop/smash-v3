"""eurocircuits_pool_profile — Eurocircuits "Pool" service capabilities.

Encodes the publicly-published rules + tolerances of the Eurocircuits
standard PCB Proto / standard pool service, plus the SEMI-FLEX pool
add-on (their milled-FR4 flex-to-install option) and the depth-routing
capability the cavity-attached-flex architecture relies on.

Sources (May 2026):

  https://www.eurocircuits.com/services/semi-flex-pool/
  https://www.eurocircuits.com/services/standard-pool/
  https://www.eurocircuits.com/technical-guidelines/designing-flex-install-pcbs/

The numbers below are the Pool service envelope (cheapest tier); custom
quotes can push these further. Designed to be the explicit replacement
for `default_fab_profile()` when the design commits to Eurocircuits as
the rigid PCB vendor.

The flex services Eurocircuits offers — and how they compose with
this profile:

  * SEMI-FLEX pool (this file's `flex` block): milled-FR4 flex, 4 or 6
    rigid layers, R_min = 5 mm. Cheapest path. Has the layer-count
    + bend-radius limits documented here.
  * Flex pool (separate service): standalone polyimide flex, 1-4 Cu
    layers, R_min ≈ 0.3 mm. Not modeled in this profile — instantiated
    as a separate FabProfile when an "attached polyimide flex tail"
    architecture wants its own DRC envelope.
  * Rigid-Flex pool: polyimide flex laminated into a rigid stack.
    Different DRC envelope again; instantiate as a separate profile.
"""
from __future__ import annotations

from smash.state.fab.laminate import Laminate
from smash.state.fab.foil import CopperFoil
from smash.state.fab.metal import MetalInsert
from smash.state.fab.tolerances import FabTolerances
from smash.state.fab.rules import DesignRules
from smash.state.fab.solder import Solder
from smash.state.fab.adhesive import Adhesive
from smash.state.fab.flex import FlexCapabilities
from smash.state.fab.milling import MillCapabilities
from smash.state.fab.profile import FabProfile


def eurocircuits_pool_profile() -> FabProfile:
    """Eurocircuits standard Pool service with SEMI-FLEX add-on."""

    # ── laminates ──────────────────────────────────────────────────────
    # Eurocircuits Pool stocks IsoLa DE 104 + DE 156 (TG 140 FR-4)
    # in the typical pressed-thickness ladder. Pulled from their
    # "Technologie standards" sheet (public PDF, May 2026).
    fr4_core = lambda t, g=None: Laminate(  # noqa: E731
        material="FR4", kind="core", thickness_um=t, thickness_tol_um=0.08 * t,
        epsilon_r=4.5, loss_tangent=0.022, glass_style=g, thermal_w_mk=0.3,
        youngs_modulus_gpa=20.0, poisson_ratio=0.30, density_kg_m3=1850.0,
        note="Isola DE104/DE156 TG 140 — Eurocircuits Pool default")
    fr4_prepreg = lambda t, g=None: Laminate(  # noqa: E731
        material="FR4", kind="prepreg", thickness_um=t, thickness_tol_um=0.08 * t,
        epsilon_r=4.5, loss_tangent=0.022, glass_style=g, thermal_w_mk=0.3,
        youngs_modulus_gpa=20.0, poisson_ratio=0.30, density_kg_m3=1850.0)
    laminates = [
        fr4_core(100, "2116"),  fr4_core(200, "2116"),
        fr4_core(360, "7628"),  fr4_core(510, "7628"),
        fr4_core(710, "7628"),
        fr4_prepreg(100, "2116"), fr4_prepreg(180, "2116"),
        fr4_prepreg(360, "7628"),
        # SEMI-FLEX inner core: 100 µm FR-4 between the inner Cu pair.
        Laminate(material="FR4", kind="core", thickness_um=100,
                 thickness_tol_um=10,
                 epsilon_r=4.5, loss_tangent=0.022, glass_style="1080",
                 thermal_w_mk=0.3, youngs_modulus_gpa=20.0,
                 poisson_ratio=0.30, density_kg_m3=1850.0,
                 note="SEMI-FLEX bend-zone central core (100 µm FR-4)"),
    ]

    # ── copper foils ───────────────────────────────────────────────────
    # Eurocircuits Pool offers 18, 35, and 70 µm Cu. The flex region in
    # SEMI-FLEX uses high-ductility (HDC) Cu at 35 µm both sides.
    foils = [
        CopperFoil(weight_oz=0.5, thickness_um=17.5, plated_thickness_um=42.5,
                   thickness_tol_um=3, placement="outer",
                   foil_type="ED", roughness_rz_um=5.5, conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0),
        CopperFoil(weight_oz=1.0, thickness_um=35.0, thickness_tol_um=4,
                   placement="inner", foil_type="ED", roughness_rz_um=5.5,
                   conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0),
        CopperFoil(weight_oz=2.0, thickness_um=70.0, thickness_tol_um=7,
                   placement="any", foil_type="ED", roughness_rz_um=6.0,
                   conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0),
        # High-ductility Cu for the SEMI-FLEX bend zone. Same thickness
        # as standard 1 oz, different annealing — survives 5 × 180°
        # without trace cracking.
        CopperFoil(weight_oz=1.0, thickness_um=35.0, thickness_tol_um=4,
                   placement="any", foil_type="HDC", roughness_rz_um=4.5,
                   conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=110.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0,
                   note="Eurocircuits SEMI-FLEX bend-zone high-ductility Cu"),
    ]

    # ── DRC rules (Pool service, Class 6) ──────────────────────────────
    # https://www.eurocircuits.com/help-knowledge-centre/standard-pool-pcb-options/
    rules = DesignRules(
        min_trace_mm=0.150,             # Pool standard Class 6: 150 µm
        min_space_mm=0.150,
        min_drill_mm=0.30,              # Pool PTH drill (HDI extends to
                                        # smaller via the buried-via add-on)
        min_via_diameter_mm=0.45,
        min_annular_ring_mm=0.125,      # Pool minimum annular ring
        max_aspect_ratio=8.0,           # 8:1 standard pool
        edge_clearance_mm=0.30,
        hole_to_hole_mm=0.30,
        silk_to_pad_mm=0.15,
        # HDI micro-via add-on (not in the base Pool; available as an
        # extension).
        micro_min_drill_mm=0.10,
        micro_min_via_diameter_mm=0.25,
        micro_min_annular_mm=0.075,
        min_board_thickness_mm=0.40,
        max_board_thickness_mm=3.20,
        note="Eurocircuits Pool service, Class 6 pattern (May 2026)",
    )

    # ── process tolerances ─────────────────────────────────────────────
    tolerances = FabTolerances(
        finished_thickness_pct=10.0,    # standard ±10% on multilayer
        etch_trace_width_um=25.0,       # ± etch over/under (Class 6)
        registration_um=50.0,           # layer-to-layer (their published
                                        # value for 8L stack)
        drill_dia_um=50.0,
        true_position_um=75.0,          # XY drill position
        impedance_pct=10.0,             # controlled-Z service ±10%
        soldermask_registration_um=75.0,
        note="Eurocircuits Pool standard tolerances",
    )

    # ── SEMI-FLEX add-on envelope ──────────────────────────────────────
    # https://www.eurocircuits.com/services/semi-flex-pool/
    flex = FlexCapabilities(
        process_name="SEMI-FLEX",
        R_min_mm=5.0,                   # Eurocircuits' official spec
        R_min_dynamic_mm=None,          # static / assembly-only
        max_bend_cycles=5,              # max 5 × 180°
        max_bend_angle_deg=180.0,
        residual_thickness_mm=0.170,    # 100 µm FR-4 core + 2 × 35 µm Cu
        residual_thickness_tol_mm=0.030,
        cu_layers_in_bend=2,
        min_flex_length_mm=3.0,
        recommended_flex_length_mm=5.0,
        min_flex_width_mm=3.0,
        min_strain_relief_mm=1.5,       # half the 3 mm min-flex-length
                                        # rule applied at each end
        min_trace_in_bend_mm=0.150,     # Class 6 in the bend zone
        min_space_in_bend_mm=0.150,
        cu_foil_type="HDC",             # high-ductility (their wording)
        allow_pth_in_bend=False,
        allow_via_in_bend=False,
        allow_pad_in_bend=False,
        require_balanced_copper=True,
        rigid_min_layers=4,
        rigid_max_layers=6,             # ← the hard cap for SEMI-FLEX pool
        note="Eurocircuits SEMI-FLEX pool — 4 or 6 layer only, assembly-"
             "only static flex (no dynamic / repeated flexing).",
    )

    # ── controlled-depth milling envelope ──────────────────────────────
    # Used by SEMI-FLEX for outer-core removal AND by the
    # cavity-attached-flex architecture for the side cavity that exposes
    # an inner Cu landing pad. Eurocircuits depth-routing tolerance from
    # their CAM team's published guidelines (May 2026).
    milling = MillCapabilities(
        available=True,
        depth_tol_mm=0.05,
        min_depth_mm=0.10,
        max_depth_mm=2.40,              # most of a 3 mm stack
        min_tool_diameter_mm=0.80,
        tool_radius_mm=0.40,
        min_pocket_wall_mm=0.50,
        min_pocket_floor_mm=0.30,
        min_pocket_opening_mm=1.0,
        side_cavity_supported=True,
        side_cavity_min_height_mm=0.50,
        side_cavity_min_width_mm=2.0,
        side_cavity_min_depth_mm=1.0,
        pad_oxide_protection="ENIG",    # default Pool surface finish
        pad_surface_roughness_um=4.0,
        position_tol_mm=0.05,
        note="Eurocircuits depth-controlled routing for SEMI-FLEX + "
             "pockets / cavities. Side cavity supported for "
             "attached-flex landing pads.",
    )

    # ── solders + adhesives (reuse the educated defaults) ─────────────
    solders = [
        Solder(name="SAC305", alloy="Sn96.5Ag3.0Cu0.5", leaded=False,
               melting_c=217, thermal_w_mk=58, cte_ppm_k=23.5,
               youngs_modulus_gpa=41, poisson_ratio=0.40,
               shear_strength_mpa=34,
               tensile_strength_mpa=35,    # bulk 50 MPa, ball pull-off ~35 MPa
               density_g_cm3=7.4),
        Solder(name="Sn63Pb37", alloy="Sn63Pb37", leaded=True,
               melting_c=183, thermal_w_mk=50, cte_ppm_k=25,
               youngs_modulus_gpa=30, poisson_ratio=0.42,
               shear_strength_mpa=27,
               tensile_strength_mpa=30,    # bulk 45 MPa, ball pull-off ~30 MPa
               density_g_cm3=8.4,
               note="leaded — runs on Eurocircuits' selective wave / "
                    "hand line; required for Smash's mixed-alloy shock "
                    "joints"),
    ]

    return FabProfile(
        name="eurocircuits-pool",
        vendor="Eurocircuits",
        process="standard pool + SEMI-FLEX add-on",
        laminates=laminates,
        foils=foils,
        metal_options=[],               # Eurocircuits Pool doesn't offer
                                        # metal-core / inlay options
        solders=solders,
        adhesives=[],                   # Pool service doesn't apply
                                        # underfills / encapsulants
        solder_processes=["reflow", "selective", "hand"],
        rules=rules,
        tolerances=tolerances,
        flex=flex,
        milling=milling,
        min_layers=1,
        max_layers=16,                  # Pool standard goes up to 16L on
                                        # rigid-only orders (SEMI-FLEX
                                        # itself caps at 6 — see flex.rigid_max_layers)
        supports_hybrid=False,          # Pool service is FR-4 only
        symmetric_required=True,
        note="Eurocircuits Pool — closest fab; supports 14L rigid + "
             "SEMI-FLEX add-on (4/6L) OR depth-routed side cavities "
             "for attached polyimide flex tails.",
    )
