"""Tests for smash.sim.thermal — RC graph builder + solver."""
import math

import pytest

from smash.state import Board, Chip, Footprint, Pad, Placement
from smash.sim.thermal import (
    build_graph, solve, evaluate_stack,
)
from smash.sim.thermal.topology import (
    _is_underfilled, _fab_kappa, _spacer_material_kappa,
    r_flex_link, r_spacer_axial, r_chip_to_tile, r_underfill,
    r_tile_to_housing_via_potting, r_tile_to_housing_via_al,
    KAPPA_CU_W_PER_MK,
)


# ── physics-helper sanity checks ────────────────────────────────────────


class TestResistanceFormulas:
    def test_flex_link_width_scaling(self):
        """Doubling width halves resistance (same Cu thickness × layers)."""
        r1 = r_flex_link(width_mm=6)
        r2 = r_flex_link(width_mm=12)
        assert r2 == pytest.approx(r1 / 2.0, rel=1e-9)

    def test_flex_link_known_value(self):
        # 12 mm × 4 layers × 17 µm Cu × 15 mm bend, κ_Cu=400 → ~46 K/W
        r = r_flex_link(width_mm=12, bend_length_m=15e-3,
                        cu_layers=4, cu_thickness_m=17e-6)
        expected = 15e-3 / (KAPPA_CU_W_PER_MK * 12e-3 * 4 * 17e-6)
        assert r == pytest.approx(expected, rel=1e-9)

    def test_spacer_axial_area_inverse(self):
        """Halving area doubles R."""
        r1 = r_spacer_axial(area_m2=1e-3, thickness_m=4e-3,
                            kappa_w_per_mk=0.3)
        r2 = r_spacer_axial(area_m2=5e-4, thickness_m=4e-3,
                            kappa_w_per_mk=0.3)
        assert r2 == pytest.approx(r1 * 2.0, rel=1e-9)

    def test_spacer_axial_al_vs_fr4(self):
        """Al (167 W/(m·K)) gives R about 0.3/167 of FR4 for the same
        geometry — the headline number for the thermal port."""
        area_m2 = math.pi * 17e-3 ** 2
        r_fr4 = r_spacer_axial(area_m2=area_m2, thickness_m=4e-3,
                               kappa_w_per_mk=0.3)
        r_al = r_spacer_axial(area_m2=area_m2, thickness_m=4e-3,
                              kappa_w_per_mk=167.0)
        assert r_fr4 / r_al == pytest.approx(167.0 / 0.3, rel=1e-9)

    def test_chip_to_tile_default_when_missing_rjc(self):
        """Chip without rth_jc_cw falls back to 30 K/W mid-range."""
        c = Chip(ref="X", manf_pn="X", footprint=None)   # rth_jc_cw=None
        r = r_chip_to_tile(c, tile_spread=8.0)
        assert r == pytest.approx(30.0 + 8.0)

    def test_underfill_R_drops_with_area(self):
        """Larger chip body → more conduction area → lower R."""
        r_small = r_underfill(4.0,  thickness_m=0.4e-3, kappa_w_per_mk=0.55)
        r_big   = r_underfill(36.0, thickness_m=0.4e-3, kappa_w_per_mk=0.55)
        assert r_big < r_small
        assert r_small / r_big == pytest.approx(9.0, rel=1e-9)

    def test_coin_under_chip_lowers_tile_spread(self):
        """A chip body sitting OVER a Cu coin gets the much smaller
        coin-pathed tile spread (≤1 K/W vs 8 K/W default)."""
        from smash.sim.thermal.topology import r_chip_to_tile_coin
        from smash.state import CuCoinInsert
        fp = Footprint(name="BGA", package_class="BGA",
                       pads=[Pad(num="1", position_mm=(0, 0),
                                  size_mm=(0.3, 0.3))],
                       size_mm=(10.0, 10.0), height_mm=1.0)
        chip = Chip(ref="X", manf_pn="X", rth_jc_cw=2.0, footprint=fp)
        board_no_coin = Board("test_no_coin")
        board_with_coin = Board("test_coin")
        board_with_coin.cu_coin_inserts = [CuCoinInsert(
            position_mm=(0, 0),
            length_mm=20.0, width_mm=20.0,
            ladder_length_mm=16.0, ladder_width_mm=16.0,
            thickness_mm=3.0, z_top_mm=3.15,
            flange_thickness_mm=0.5, kind="T",
            corner_chamfer_radius_mm=5.0,
        )]
        # Chip at the board centre sits over the coin's flange.
        r_over, tag_over = r_chip_to_tile_coin(chip, (0.0, 0.0),
                                               board_with_coin)
        r_bare, tag_bare = r_chip_to_tile_coin(chip, (0.0, 0.0),
                                               board_no_coin)
        # Same chip placed at a corner that's outside the 20×20 coin —
        # gets "near coin" benefit but not the full over-coin shortcut.
        r_near, tag_near = r_chip_to_tile_coin(chip, (12.0, 12.0),
                                               board_with_coin)
        assert r_over < r_near < r_bare
        assert "coin(over)" in tag_over
        assert "coin(near)" in tag_near
        assert tag_bare == ""


# ── BGA classifier ─────────────────────────────────────────────────────


class TestBGAClassifier:
    def _chip(self, fp_name: str = "", pkg_class: str = "") -> Chip:
        fp = Footprint(name=fp_name, package_class=pkg_class,
                       pads=[Pad(num="1", position_mm=(0, 0),
                                 size_mm=(0.3, 0.3))])
        return Chip(ref="X", manf_pn="X", footprint=fp)

    def test_bga_detected(self):
        assert _is_underfilled(self._chip(fp_name="MyChip_BGA169"))
        assert _is_underfilled(self._chip(pkg_class="WLCSP"))
        assert _is_underfilled(self._chip(fp_name="Pkg_TFBGA"))

    def test_non_bga_rejected(self):
        assert not _is_underfilled(self._chip(fp_name="X_QFN32"))
        assert not _is_underfilled(self._chip(pkg_class="LQFP"))
        assert not _is_underfilled(self._chip(fp_name="MyPart_DFN"))

    def test_empty_footprint_handled(self):
        c = Chip(ref="X", manf_pn="X", footprint=None)
        assert not _is_underfilled(c)


# ── fab lookups + spacer material → κ ───────────────────────────────────


class TestFabLookups:
    def test_default_fab_encapsulant_kappa(self):
        """Stycast 2651MM in the default profile gives 0.6 W/(m·K)."""
        from smash import default_fab_profile
        k = _fab_kappa(default_fab_profile(),
                       "adhesive_encapsulant", default=999.0)
        assert k == pytest.approx(0.6)

    def test_default_fab_underfill_kappa(self):
        """Eccobond UF1173 gives 0.55 W/(m·K)."""
        from smash import default_fab_profile
        k = _fab_kappa(default_fab_profile(),
                       "adhesive_underfill", default=999.0)
        assert k == pytest.approx(0.55)

    def test_default_fab_aluminium_kappa(self):
        from smash import default_fab_profile
        k = _fab_kappa(default_fab_profile(), "metal_al", default=999.0)
        assert k == pytest.approx(167.0)

    def test_spacer_material_fr4(self):
        from smash import default_fab_profile
        b = Board("test_board", spacer_material="fr4")
        assert _spacer_material_kappa(b, default_fab_profile()) \
            == pytest.approx(0.3)

    def test_spacer_material_aluminium(self):
        from smash import default_fab_profile
        b = Board("test_board", spacer_material="aluminium")
        assert _spacer_material_kappa(b, default_fab_profile()) \
            == pytest.approx(167.0)

    def test_no_fab_falls_back(self):
        """A None fab profile uses the documented defaults."""
        assert _fab_kappa(None, "adhesive_encapsulant", default=0.6) == 0.6
        assert _fab_kappa(None, "metal_al", default=167.0) == 167.0


# ── graph build + solve ────────────────────────────────────────────────


def _bga_chip(ref: str, p_active: float, rjc: float, tj: float) -> Chip:
    """Make a tiny BGA-class chip with thermal specs populated."""
    fp = Footprint(name="MyChip_BGA", package_class="FBGA",
                   pads=[Pad(num="1", position_mm=(0, 0),
                             size_mm=(0.3, 0.3))],
                   size_mm=(4.0, 4.0), height_mm=1.2)
    return Chip(ref=ref, manf_pn=ref, footprint=fp,
                p_active_w=p_active, p_max_w=p_active,
                rth_jc_cw=rjc, tj_max_c=tj)


def _stack_two_tiles_one_spacer():
    """Build a tiny snake: rigid → spacer → rigid, populated with a chip
    on each rigid tile so the solver has work to do."""
    a = Board("a", spacer_floor_above_mm=2.0, spacer_material="fr4")
    a.set_fitted_stackup()
    sp = Board("sp_a_b", kind="spacer")
    b = Board("b", spacer_floor_below_mm=2.0, spacer_material="fr4")
    b.set_fitted_stackup()
    a.chip_placements.append(Placement(
        (0, 0), 0.0, _bga_chip("U_A", p_active=1.0, rjc=8.0, tj=125.0),
        "top", False))
    b.chip_placements.append(Placement(
        (0, 0), 0.0, _bga_chip("U_B", p_active=0.5, rjc=10.0, tj=125.0),
        "top", False))
    boards = {"a": a, "sp_a_b": sp, "b": b}
    chain = ["a", "sp_a_b", "b"]
    return chain, boards


class TestGraphBuildAndSolve:
    def test_graph_has_expected_node_kinds(self):
        chain, boards = _stack_two_tiles_one_spacer()
        g = build_graph(chain, boards, fab=None)
        kinds = {n.name: n.kind for n in g.nodes.values()}
        assert kinds["housing"] == "housing"
        assert kinds["body:a"] == "tile_body"
        assert kinds["body:sp_a_b"] == "spacer_body"
        assert kinds["body:b"] == "tile_body"
        assert kinds["die:a/U_A"] == "die"
        assert kinds["die:b/U_B"] == "die"

    def test_housing_is_boundary_at_ambient(self):
        chain, boards = _stack_two_tiles_one_spacer()
        g = build_graph(chain, boards, fab=None, t_ambient_c=25.0)
        assert g.nodes["housing"].t_fixed_c == 25.0

    def test_die_power_injected(self):
        chain, boards = _stack_two_tiles_one_spacer()
        g = build_graph(chain, boards, fab=None)
        assert g.nodes["die:a/U_A"].p_input_w == pytest.approx(1.0)
        assert g.nodes["die:b/U_B"].p_input_w == pytest.approx(0.5)

    def test_p_max_mode(self):
        chain, boards = _stack_two_tiles_one_spacer()
        # Bump only U_A's p_max so we see the mode flip.
        boards["a"].chip_placements[0].item.p_max_w = 5.0
        g_active = build_graph(chain, boards, fab=None, use_p_max=False)
        g_max = build_graph(chain, boards, fab=None, use_p_max=True)
        assert g_active.nodes["die:a/U_A"].p_input_w == pytest.approx(1.0)
        assert g_max.nodes["die:a/U_A"].p_input_w == pytest.approx(5.0)

    def test_solve_returns_per_node_temps(self):
        chain, boards = _stack_two_tiles_one_spacer()
        g = build_graph(chain, boards, fab=None)
        temps = solve(g)
        assert "die:a/U_A" in temps
        assert "die:b/U_B" in temps
        assert "body:a" in temps
        # Housing stays pinned.
        assert temps["housing"] == pytest.approx(25.0, abs=1e-9)
        # Die is hotter than its tile body (heat flows out).
        assert temps["die:a/U_A"] > temps["body:a"]
        assert temps["die:b/U_B"] > temps["body:b"]
        # All bodies above ambient.
        assert temps["body:a"] > 25.0
        assert temps["body:b"] > 25.0

    def test_higher_power_runs_hotter(self):
        chain, boards = _stack_two_tiles_one_spacer()
        # Boost U_A; U_B unchanged.
        boards["a"].chip_placements[0].item.p_active_w = 5.0
        g = build_graph(chain, boards, fab=None)
        temps = solve(g)
        assert temps["die:a/U_A"] > temps["die:b/U_B"]

    def test_no_chip_skipped(self):
        """A chip with p_active_w=0 doesn't add a die node (would be
        irrelevant heat-flow-wise)."""
        chain, boards = _stack_two_tiles_one_spacer()
        boards["a"].chip_placements[0].item.p_active_w = 0
        boards["a"].chip_placements[0].item.p_max_w = 0
        g = build_graph(chain, boards, fab=None)
        assert "die:a/U_A" not in g.nodes


class TestAlSpacerHelpsCooler:
    """Cross-link with the bend-sim Al-spacer decision: Al should make
    the snake conduct heat between tiles much better than FR4."""

    def test_al_spacers_cool_chip_more_than_fr4(self):
        # Same stack, only spacer_material changes.
        chain, boards_fr4 = _stack_two_tiles_one_spacer()
        _, boards_al = _stack_two_tiles_one_spacer()
        for b in boards_al.values():
            if b.kind == "rigid":
                b.spacer_material = "aluminium"
        from smash import default_fab_profile
        fab = default_fab_profile()
        # Use a single hot chip so the conduction path matters.
        for boards in (boards_fr4, boards_al):
            boards["a"].chip_placements[0].item.p_active_w = 3.0
        g_fr4 = build_graph(chain, boards_fr4, fab=fab)
        g_al = build_graph(chain, boards_al, fab=fab)
        t_fr4 = solve(g_fr4)
        t_al = solve(g_al)
        # The Al-spacer config doesn't dramatically change the chip's
        # PRIMARY conductance to housing (potting + edge dominates that),
        # but it DOES couple body:a to body:b much more tightly. The
        # OTHER tile heating up confirms the path is doing work.
        assert t_al["body:b"] > t_fr4["body:b"]


# ── evaluate_stack — end-to-end orchestration ─────────────────────────


class TestEvaluateStack:
    def test_result_has_dies_and_tiles(self):
        chain, boards = _stack_two_tiles_one_spacer()
        r = evaluate_stack(chain, boards, fab=None)
        refs = {d.ref for d in r.dies}
        assert refs == {"U_A", "U_B"}
        tile_names = {t.tile for t in r.tiles}
        assert tile_names == {"a", "sp_a_b", "b"}

    def test_pass_when_t_jmax_high(self):
        chain, boards = _stack_two_tiles_one_spacer()
        r = evaluate_stack(chain, boards, fab=None)
        assert all(d.verdict == "pass" for d in r.dies)
        assert r.worst_die.headroom_k > 10.0

    def test_fail_when_t_jmax_low(self):
        chain, boards = _stack_two_tiles_one_spacer()
        for b in boards.values():
            for pl in b.chip_placements:
                pl.item.tj_max_c = 30.0      # almost at ambient
                pl.item.p_active_w = 5.0     # crank up the heat
        r = evaluate_stack(chain, boards, fab=None)
        assert any(d.verdict == "fail" for d in r.dies)
