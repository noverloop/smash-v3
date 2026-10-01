"""default_fab_profile — an educated-guess fab, to be replaced later.

PLACEHOLDER: a plausible mainstream multilayer / HDI house. The catalog
is seeded from materials already in the project (FR4 ε4.5 and "FR4 thin"
ε4.2 from the export's `_STACKUP_BLOCK`, plus the RO4350B and Oak-Mitsui
HK04 named in `state/stackup/dielectric.py`) and the DRC numbers from the
project's `.kicad_dru`. Swap in the real fab's data sheet when known —
nothing should depend on these exact values beyond as defaults.
"""
from __future__ import annotations

from smash.state.fab.laminate import Laminate
from smash.state.fab.foil import CopperFoil
from smash.state.fab.metal import MetalInsert
from smash.state.fab.tolerances import FabTolerances
from smash.state.fab.rules import DesignRules
from smash.state.fab.solder import Solder
from smash.state.fab.adhesive import Adhesive
from smash.state.fab.profile import FabProfile


def default_fab_profile() -> FabProfile:
    """A representative HDI-capable fab profile (placeholder)."""
    fr4_core = lambda t, g=None: Laminate(  # noqa: E731
        material="FR4", kind="core", thickness_um=t, thickness_tol_um=0.1 * t,
        epsilon_r=4.5, loss_tangent=0.02, glass_style=g, thermal_w_mk=0.3,
        youngs_modulus_gpa=20.0, poisson_ratio=0.30, density_kg_m3=1850.0)
    fr4_prepreg = lambda t, g=None: Laminate(  # noqa: E731
        material="FR4", kind="prepreg", thickness_um=t, thickness_tol_um=0.1 * t,
        epsilon_r=4.5, loss_tangent=0.02, glass_style=g, thermal_w_mk=0.3,
        youngs_modulus_gpa=20.0, poisson_ratio=0.30, density_kg_m3=1850.0)

    laminates = [
        # FR4 cores + prepregs across the common pressed thicknesses.
        fr4_core(50, "1080"), fr4_core(100, "2116"), fr4_core(150, "3313"),
        fr4_core(200), fr4_core(360), fr4_core(710),
        fr4_prepreg(50, "1080"), fr4_prepreg(100, "2116"), fr4_prepreg(150, "3313"),
        # "FR4 thin" — the embedded-cap dielectric used in _STACKUP_BLOCK.
        Laminate(material="FR4 thin", kind="core", thickness_um=50,
                 thickness_tol_um=5, epsilon_r=4.2, loss_tangent=0.02,
                 thermal_w_mk=0.3, youngs_modulus_gpa=22.0, poisson_ratio=0.30,
                 density_kg_m3=1850.0, note="embedded-cap thin core"),
        # Rogers high-frequency laminate (hybrid stackups).
        Laminate(material="RO4350B", kind="core", thickness_um=127,
                 thickness_tol_um=12, epsilon_r=3.48, loss_tangent=0.0037,
                 thermal_w_mk=0.69, youngs_modulus_gpa=9.0, poisson_ratio=0.35,
                 density_kg_m3=2170.0, note="5 mil, RF layers"),
        # Oak-Mitsui buried-capacitance laminate.
        Laminate(material="Oak-Mitsui HK04", kind="core", thickness_um=14,
                 thickness_tol_um=2, epsilon_r=4.0, loss_tangent=0.02,
                 youngs_modulus_gpa=20.0, poisson_ratio=0.30,
                 density_kg_m3=1850.0, note="buried capacitance"),
    ]

    # `elongation_pct` = RT elongation-at-break (ductility), the property
    # that sets bend / crack-bridging survival (smash.sim.fea.trace_strain).
    # Standard ED ≈ 10 % (thin/cold ED can drop to ~3 %, the conservative
    # floor). `min_processed_thickness_um` = NCAB Stackups guide inner
    # copper-after-processing minimum (18→11.4, 35→24.9, 70→55.7 µm) — the
    # worst-case t for thickness-driven mechanical checks.
    foils = [
        CopperFoil(weight_oz=0.5, thickness_um=17.5, plated_thickness_um=42.5,
                   thickness_tol_um=3, placement="outer",
                   foil_type="ED", roughness_rz_um=5.5, conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0,
                   elongation_pct=10.0, min_processed_thickness_um=11.4),
        CopperFoil(weight_oz=1.0, thickness_um=35.0, thickness_tol_um=4,
                   placement="inner",
                   foil_type="ED", roughness_rz_um=5.5, conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0,
                   elongation_pct=10.0, min_processed_thickness_um=24.9),
        CopperFoil(weight_oz=2.0, thickness_um=70.0, thickness_tol_um=7,
                   placement="any",
                   foil_type="ED", roughness_rz_um=6.0, conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0,
                   elongation_pct=12.0, min_processed_thickness_um=55.7),
        # SIW / mmWave "special copper": hyper-very-low-profile foil for
        # the radar's substrate-integrated waveguides on the Rogers layers.
        # HVLP is a *roughness* class — still ED copper, so ED ductility.
        CopperFoil(weight_oz=0.5, thickness_um=17.5, thickness_tol_um=3,
                   placement="any", foil_type="HVLP", roughness_rz_um=1.5,
                   conductivity_s_m=5.8e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0,
                   elongation_pct=10.0, min_processed_thickness_um=11.4,
                   note="SIW / mmWave low-loss foil (radar Rogers layers)"),
        # Rolled-annealed (wrought) foil — a DIFFERENT copper sheet, not a
        # finish: rolled + annealed → equiaxed grains, high RT elongation
        # (~20 %). The flex/bend-endurance choice; carry it as an available
        # option for shock-/flex-critical layers (vs the brittler ED above).
        CopperFoil(weight_oz=1.0, thickness_um=35.0, thickness_tol_um=4,
                   placement="any", foil_type="RA", roughness_rz_um=3.0,
                   conductivity_s_m=5.85e7,
                   youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                   density_kg_m3=8960.0,
                   elongation_pct=20.0, min_processed_thickness_um=24.9,
                   note="rolled-annealed (Type W) ductile foil — flex / "
                        "shock-strain endurance; ~20% elongation vs ED ~10%"),
    ]

    metal_options = [
        MetalInsert(material="aluminium", role="backing", thickness_mm=0.5,
                    thickness_tol_mm=0.05, thermal_w_mk=167, cte_ppm_k=23,
                    youngs_modulus_gpa=70.0, poisson_ratio=0.33,
                    density_kg_m3=2700.0, yield_strength_mpa=270.0,
                    note="thermal spreader / stiffener (Al 6061)"),
        MetalInsert(material="aluminium", role="backing", thickness_mm=1.0,
                    thickness_tol_mm=0.05, thermal_w_mk=167, cte_ppm_k=23,
                    youngs_modulus_gpa=70.0, poisson_ratio=0.33,
                    density_kg_m3=2700.0, yield_strength_mpa=270.0),
        MetalInsert(material="copper", role="coin", thickness_mm=1.0,
                    thickness_tol_mm=0.05, thermal_w_mk=390, cte_ppm_k=17,
                    youngs_modulus_gpa=117.0, poisson_ratio=0.34,
                    density_kg_m3=8960.0, yield_strength_mpa=70.0,
                    note="pressed-in slug under hot dies"),
    ]

    solders = [
        Solder(name="SAC305", alloy="Sn96.5Ag3.0Cu0.5", leaded=False,
               melting_c=217, thermal_w_mk=58, cte_ppm_k=23.5,
               youngs_modulus_gpa=41, poisson_ratio=0.40,
               shear_strength_mpa=34, tensile_strength_mpa=35,
               density_g_cm3=7.4,
               note="default lead-free reflow paste"),
        Solder(name="Sn63Pb37", alloy="Sn63Pb37", leaded=True,
               melting_c=183, thermal_w_mk=50, cte_ppm_k=25,
               youngs_modulus_gpa=30, poisson_ratio=0.42,
               shear_strength_mpa=27, tensile_strength_mpa=30,
               density_g_cm3=8.4,
               note="eutectic leaded (rework / hand)"),
        # Low-temp eutectic In-Sn for the aft battery joint. The Tadiran
        # TLM-1520HPM/S cells can't see a SAC305 reflow (~245 °C) — their
        # safety qualification tops out at a 150 °C oven — so the cell-tab
        # joints use In52/Sn48 (liquidus 118 °C, peak ~135-145 °C, under the
        # cell limit). Ductile (good for the setback joint, unlike brittle
        # Sn-Bi). Mechanical constants left None: this joint is not a
        # launch-FEA target (the potting + hard seating carry the cell mass;
        # the joint is electrical). Properties beyond the eutectic point are
        # nominal handbook values — confirm a specific In-Sn reflow profile
        # with Tadiran before production.
        Solder(name="In52Sn48", alloy="In52Sn48", leaded=False,
               melting_c=118, thermal_w_mk=34, cte_ppm_k=28,
               density_g_cm3=7.30,
               note="low-temp eutectic In-Sn (118 °C) — aft cell-tab joints "
                    "so the Li-primary cells stay under their 150 °C limit; "
                    "the final battery↔activation step is reflowed in this "
                    "alloy as the last step before potting"),
    ]

    adhesives = [
        # Capillary underfill — Henkel "LOCTITE ECCOBOND UF1173 Data
        # Package" (Nov 2018, internal webinar deck, in Research/).
        # ADAS-grade automotive BGA/CSP underfill. Single-component,
        # 5 min @ 150 °C thermal cure.
        Adhesive(name="Loctite Eccobond UF1173", role="underfill",
                 thermal_w_mk=0.55, cte_ppm_k=26, cte_above_tg_ppm_k=103,
                 youngs_modulus_gpa=5.9,           # flex modulus (DMA, 25 °C)
                 poisson_ratio=0.30,               # 63 % filled epoxy
                 tg_c=160,                         # TMA, glass-transition knee
                 filler_pct=63, density_g_cm3=1.69,
                 viscosity_cps=5_330,              # rheometer, 1 s⁻¹ @ 25 °C
                 note="capillary BGA/CSP underfill — Eccobond UF1173"),
        # WBA55 WLCSP die-area underfill named on the part factory as
        # "Hysol FP4549 or equivalent capillary underfill" (see
        # parts/mcus.py). The placeholder fab stocks the UF1173 equivalent,
        # so model FP4549's structural constants as identical to the
        # ground-truth UF1173 until the Henkel FP4549 TDS is pulled. Lets
        # the launch-FEA resolve the WBA55/WLCSP joints on wakeup_board.
        Adhesive(name="Hysol_FP4549_capillary_die_area", role="underfill",
                 thermal_w_mk=0.55, cte_ppm_k=26, cte_above_tg_ppm_k=103,
                 youngs_modulus_gpa=5.9, poisson_ratio=0.30,
                 tg_c=160, filler_pct=63, density_g_cm3=1.69,
                 viscosity_cps=5_330,
                 note="WLCSP die-area underfill (Hysol FP4549 'or "
                      "equivalent') — modeled as the characterized Eccobond "
                      "UF1173 pending the FP4549 datasheet"),
        # Vacuum-potting encapsulant — Henkel "LOCTITE STYCAST 2651MM
        # CAT 23LV" TDS (April 2020, in Research/). Black filled epoxy,
        # mixed viscosity ~30 000 cP, Shore D 86 ⇒ E ≈ 4 GPa. The
        # CAT 23LV catalyst variant is the low-viscosity option (25 cP
        # catalyst vs 35 000 cP resin) — flowable under vacuum through
        # the Ø3 mm potting holes (~660 mm³/s per hole at −0.5 bar, see
        # `tools/run_bend_sim.py` notes). Thermal conductivity 0.6 W/(m·K)
        # gives ~3.3× better heat removal from PMICs / SoC / AWR
        # than the unfilled clear 1266. Op range -65 to +125 °C.
        # Selected as the design's default encapsulant because the
        # +33–67 % forward-G envelope across the bottleneck boards
        # (radar, companion_compute, activation_interface, camera) is
        # worth the loss of visual inspectability through the cured
        # potting. The Ø3 potting-hole geometry was the gate that made
        # this viable; at Ø2 the viscosity was marginal.
        Adhesive(name="Stycast 2651MM CAT 23LV", role="encapsulant",
                 thermal_w_mk=0.6, cte_ppm_k=51.3,
                 youngs_modulus_gpa=4.0,           # from Shore D 86 + flex
                                                   # strength 104 MPa (TDS)
                 poisson_ratio=0.34,               # filled epoxy, mid-range
                 tg_c=120,                         # estimated from op-range
                                                   # ceiling (125 °C)
                 density_g_cm3=1.52,               # mixed (TDS)
                 viscosity_cps=30_000,             # mixed estimate (100:15
                                                   # resin@35 000 + cat@25)
                 note="black filled vacuum-potting encapsulant for the "
                      "folded stack — Stycast 2651MM CAT 23LV (chosen "
                      "over 1266 for ~+50 % bend envelope and 3.3× "
                      "better thermal conductivity)"),
        # Alternative encapsulant — Henkel "LOCTITE STYCAST 1266 A/B"
        # TDS (2003 Emerson & Cuming, in Research/). Two-component,
        # CLEAR epoxy at very low mixed viscosity (650 cP); the
        # transparency lets the assembly be visually inspected through
        # the potting. Mechanically softer (Shore D 75 ⇒ E ≈ 3 GPa) and
        # less thermally conductive (0.18 W/(m·K) — borrowed from 1090's
        # similar unfilled resin since the 1266 TDS doesn't quote it).
        # Kept in the catalogue as a fall-back for prototype debug runs
        # where being able to look at solder joints through the potting
        # matters more than the extra mechanical / thermal margin.
        Adhesive(name="Stycast 1266", role="encapsulant",
                 thermal_w_mk=0.18, cte_ppm_k=60,
                 youngs_modulus_gpa=3.0, poisson_ratio=0.34,
                 tg_c=100, density_g_cm3=1.12,
                 viscosity_cps=650,
                 note="alternative clear low-viscosity encapsulant — "
                      "softer + lower κ than 2651MM but inspectable "
                      "through the cured potting"),
    ]

    return FabProfile(
        name="generic-hdi-placeholder",
        vendor=None,
        process="multilayer + laser-microvia HDI",
        laminates=laminates,
        foils=foils,
        metal_options=metal_options,
        solders=solders,
        adhesives=adhesives,
        # reflow line + selective/hand for THT & connectors + step-melt:
        # a second alloy beyond the board paste is supported.
        solder_processes=["reflow", "selective", "hand", "step"],
        rules=DesignRules(),          # harvested .kicad_dru defaults
        tolerances=FabTolerances(),   # ±10% thickness, ±25µm etch, ...
        min_layers=1,
        max_layers=20,
        supports_hybrid=True,
        symmetric_required=True,
        note="EDUCATED-GUESS PLACEHOLDER — replace with the real fab's data.",
    )
