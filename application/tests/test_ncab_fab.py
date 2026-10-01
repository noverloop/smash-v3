"""Tests for the NCAB-grounded fab rule family (smash.state.fab.ncab).

Additive profile family: NCAB design-guideline DRC rules / tolerances /
cavity-milling layered on the project's default material catalog, with
per-board cheapest-tier selection. Does not touch default_fab_profile or
eurocircuits_pool (those have their own tests)."""

import pytest

from smash import Design
from smash.state.fab import (
    ncab_profile, get_fab_profile, select_ncab_profile_name,
    min_tier_for_pitch, default_fab_profile,
)


class TestNcabRules:
    def test_advanced_hdi_trace_gap_match_guide(self):
        # HDI guide, 0.50 mm BGA escape, advanced: track/gap 75/87 µm.
        r = ncab_profile(tier="advanced", hdi=True, finest_pitch_mm=0.50).rules
        assert r.min_trace_mm == 0.075
        assert r.min_space_mm == 0.087

    def test_general_tier_plain_multilayer(self):
        r = ncab_profile(tier="general").rules
        assert r.min_trace_mm == 0.150
        assert r.min_space_mm == 0.200

    def test_annular_tightens_general_to_advanced(self):
        assert ncab_profile(tier="general").rules.min_annular_ring_mm == 0.200
        assert ncab_profile(tier="advanced").rules.min_annular_ring_mm == 0.125

    def test_milling_grounded_in_copper_coin_guide(self):
        m = ncab_profile().milling
        assert m.available and m.depth_tol_mm == 0.1


class TestCatalogReuse:
    """ncab_profile must reuse the project default catalog, not duplicate it."""

    def test_materials_come_from_default(self):
        base = default_fab_profile()
        p = ncab_profile(tier="advanced", hdi=True)
        assert [s.name for s in p.solders] == [s.name for s in base.solders]
        assert len(p.laminates) == len(base.laminates)
        assert [m.material for m in p.metal_options] == [m.material for m in base.metal_options]


class TestTierSelection:
    def test_cheapest_tier_for_pitch(self):
        assert min_tier_for_pitch(0.50) == "moderate"
        assert min_tier_for_pitch(0.65) == "general"
        assert min_tier_for_pitch(None) is None

    def test_sub_uhdi_pitch_flagged(self):
        with pytest.raises(ValueError, match="Ultra-HDI"):
            min_tier_for_pitch(0.35)


class TestRegistry:
    def test_none_resolves_to_default(self):
        assert get_fab_profile(None).name == default_fab_profile().name

    def test_named_profiles_resolve(self):
        assert get_fab_profile("ncab-class3-moderate-hdi").name == "ncab-class3-moderate-hdi"
        assert get_fab_profile("ncab-class3-general").name == "ncab-class3-general"

    def test_unknown_name_raises(self):
        with pytest.raises(KeyError):
            get_fab_profile("ncab-nonsense")


class TestPerBoardSelection:
    def test_pad_only_board_gets_general(self):
        # A board with no area-array part → plain multilayer (general).
        d = Design()
        assert select_ncab_profile_name([]) == "ncab-class3-general"
