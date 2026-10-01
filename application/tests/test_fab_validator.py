"""Tests for smash.validators.fab.check_fab_rules — routed geometry vs.
the FabProfile DRC envelope."""

import pathlib

import pytest

from smash import Board, Track, Via
from smash.validators import check_fab_rules
from smash.state.routing.ingest import import_session

from smash.roots import git_repo_root

_SES = (git_repo_root()
        / "output" / "kicad_pcbs" / "smash_evb_snake" / "smash_evb_snake.ses")


class TestCheckFabRules:
    def test_subspec_track_flagged(self):
        b = Board(name="flight_board", kind="rigid")
        b.tracks.append(Track(net="N", layer="F.Cu", width_mm=0.10,
                              path=[(0, 0), (1, 0)]))           # < 0.20 min
        issues = check_fab_rules({"flight_board": b})
        rules = {i.rule for i in issues}
        assert "min_trace" in rules
        # the offending net is carried in refs
        assert any("N" in i.refs for i in issues if i.rule == "min_trace")

    def test_subspec_via_flagged(self):
        b = Board(name="flight_board", kind="rigid")
        b.vias.append(Via(net="GND", position_mm=(0, 0), drill_mm=0.10,
                          pad_diameter_mm=0.20))                # drill + Ø + annular all under
        rules = {i.rule for i in check_fab_rules({"flight_board": b})}
        assert {"min_drill", "min_via_diameter", "min_annular_ring"} <= rules

    def test_clean_board_passes(self):
        b = Board(name="flight_board", kind="rigid")
        b.tracks.append(Track(net="N", layer="In3", width_mm=0.25,
                              path=[(0, 0), (1, 1)]))
        b.vias.append(Via(net="GND", position_mm=(0, 0), drill_mm=0.30,
                          pad_diameter_mm=0.60))
        assert check_fab_rules({"flight_board": b}) == []

    @pytest.mark.skipif(not _SES.exists(), reason="routed session not present")
    def test_imported_ses_board_is_drc_clean(self):
        # A real KiCad-routed board (0.2 mm tracks, 0.3/0.6 mm vias) must
        # pass the default fab profile — it was routed under those rules.
        pr = import_session(_SES)
        b = Board(name="flight_board", kind="rigid")
        b.tracks, b.vias = pr.tracks, pr.vias
        assert check_fab_rules({"flight_board": b}) == []


class TestCheckPanelFlex:
    """Flex DRC against the panel — every snake link + every branch's
    available length is compared against the fab's R_min/strain-relief."""

    def test_eurocircuits_pool_flags_all_snake_links_short(self):
        # Current Smash panel: 44 mm pitch − Ø34 tile = 10 mm gap per
        # link. Eurocircuits SEMI-FLEX requires π·5 + 2·1.5 = 18.71 mm.
        # Every snake link should error.
        from smash.layout.boards.smash_evb_v1 import build_panel
        from smash.state.fab import eurocircuits_pool_profile
        from smash.validators.fab import check_panel_flex
        fab = eurocircuits_pool_profile()
        panel, boards = build_panel()
        issues = check_panel_flex(panel, boards, profile=fab)
        too_short = [i for i in issues if i.rule == "flex_zone_too_short"
                     and "↔" in i.message]  # snake links only
        assert len(too_short) == len(panel.snake_chain) - 1
        # Each shortage is 18.71 − 10.0 = 8.71 mm
        for i in too_short:
            assert "short by 8.7 mm" in i.message

    def test_eurocircuits_flags_14L_rigid_too_many_for_semi_flex(self):
        # SEMI-FLEX caps at 6 rigid layers. A 14L board should error.
        from smash.state.fab import eurocircuits_pool_profile
        fab = eurocircuits_pool_profile()
        issues = fab.check_flex_layer_count(14)
        assert any(i.rule == "flex_rigid_too_many_layers" for i in issues)
        # 6L passes
        assert fab.check_flex_layer_count(6) == []
        # 4L passes (min)
        assert fab.check_flex_layer_count(4) == []
        # 2L is below the SEMI-FLEX min
        issues_2L = fab.check_flex_layer_count(2)
        assert any(i.rule == "flex_rigid_too_few_layers" for i in issues_2L)

    def test_default_fab_no_flex_means_no_flex_errors(self):
        # Default placeholder fab has no FlexCapabilities populated →
        # flex DRC is a no-op (R_min_mm is None).
        from smash.layout.boards.smash_evb_v1 import build_panel
        from smash.state.fab import default_fab_profile
        from smash.validators.fab import check_panel_flex
        panel, boards = build_panel()
        assert check_panel_flex(panel, boards, profile=default_fab_profile()) == []


class TestCheckPanelCavities:
    """Spacer-cavity DRC against the milling envelope."""

    def test_eurocircuits_pool_cavities_pass(self):
        # Smash spacer cavities are well within Eurocircuits' depth /
        # opening / floor limits.
        from smash.layout.boards.smash_evb_v1 import build_panel
        from smash.state.fab import eurocircuits_pool_profile
        from smash.validators.fab import check_panel_cavities
        fab = eurocircuits_pool_profile()
        _panel, boards = build_panel()
        assert check_panel_cavities(boards, profile=fab) == []

    def test_check_side_cavity_unsupported_fails_fast(self):
        # The default profile doesn't enable side cavities — attempts to
        # validate one should produce a single targeted error.
        from smash.state.fab import default_fab_profile
        fab = default_fab_profile()
        issues = fab.check_side_cavity(width_mm=4.0, depth_mm=1.5)
        assert len(issues) == 1
        assert issues[0].rule == "side_cavity_unsupported"

    def test_eurocircuits_side_cavity_passes_for_typical_attach(self):
        # Attached-flex landing cavity sized typically: 4 mm wide (flex
        # strip width), 1.5 mm deep (into the rigid edge), exposed-layer
        # height ~0.6 mm. Within Eurocircuits' envelope.
        from smash.state.fab import eurocircuits_pool_profile
        fab = eurocircuits_pool_profile()
        assert fab.check_side_cavity(
            width_mm=4.0, depth_mm=1.5, height_mm=0.6) == []

    def test_eurocircuits_pocket_too_deep(self):
        from smash.state.fab import eurocircuits_pool_profile
        fab = eurocircuits_pool_profile()
        # Max depth is 2.4 mm; ask for 3 mm
        issues = fab.check_pocket(depth_mm=3.0)
        assert any(i.rule == "pocket_too_deep" for i in issues)
