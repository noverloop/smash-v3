"""smash.state.fab — the factory capability model.

A `FabProfile` is the single authority on what the PCB house can build
(laminate / foil / metal-insert catalog) and the limits it imposes (DRC
`rules`, process `tolerances`). The stackup fitter, 3D-mesh builder, and
DRC all constrain against it — "our limit is the factory, not ourselves".
"""
from smash.state.fab.laminate import Laminate
from smash.state.fab.foil import CopperFoil, OZ_TO_UM
from smash.state.fab.metal import MetalInsert
from smash.state.fab.tolerances import FabTolerances
from smash.state.fab.rules import DesignRules
from smash.state.fab.solder import Solder
from smash.state.fab.adhesive import Adhesive
from smash.state.fab.flex import FlexCapabilities
from smash.state.fab.milling import MillCapabilities
from smash.state.fab.profile import FabProfile
from smash.state.fab.default import default_fab_profile
from smash.state.fab.eurocircuits_pool import eurocircuits_pool_profile
# NCAB-grounded rule family (additive): DRC rules/tolerances/cavity-milling
# from the NCAB design guidelines, layered on the default material catalog,
# with per-board cheapest-tier selection.
from smash.state.fab.ncab import (
    ncab_profile, get_fab_profile, select_ncab_profile,
    select_ncab_profile_name, assign_board_fabs,
    min_tier_for_pitch, finest_bga_pitch_mm,
)

__all__ = [
    "Laminate", "CopperFoil", "OZ_TO_UM", "MetalInsert",
    "Solder", "Adhesive",
    "FabTolerances", "DesignRules",
    "FlexCapabilities", "MillCapabilities",
    "FabProfile", "default_fab_profile", "eurocircuits_pool_profile",
    # NCAB rule family
    "ncab_profile", "get_fab_profile", "select_ncab_profile",
    "select_ncab_profile_name", "assign_board_fabs",
    "min_tier_for_pitch", "finest_bga_pitch_mm",
]
