"""smash.sim.battery — cell model anchors, power-tree math, mission plumbing."""
from __future__ import annotations

import pytest

from smash.sim.battery import loads as L
from smash.sim.battery.cells import PACK_3X_1520HPM, validate_rows
from smash.sim.battery.mission import (build_profile, first_failure, max_descent_s,
                                       run_mission)
from smash.sim.battery.power_tree import Load, solve_tree


@pytest.mark.parametrize("row", validate_rows(), ids=lambda r: f"{r[0]}@{r[1]}A")
def test_cell_model_matches_datasheet_capacity(row):
    _name, _amps, _vcut, ds, sim, _src = row
    assert abs(sim - ds) / ds < 0.03


def test_boost_is_constant_power_and_passes_through_above_vout():
    ld = [Load("x", "3V3", 0.30)]
    lo, hi = solve_tree(ld, 3.0), solve_tree(ld, 3.6)
    assert lo.i_bat > hi.i_bat                          # sagging cell -> more current
    bypass = solve_tree(ld, 4.0)                        # >= 3.87 V: MCP1640 passes VIN
    assert bypass.convs["U_BOOST"].mode == "bypass"
    assert bypass.i_bat == pytest.approx(0.30, rel=0.01)


def test_mcp1640_bypass_abs_max_is_flagged():
    t = solve_tree([Load("x", "3V3", 0.45)], 4.0)
    assert any("bypass" in f for f in t.flags())


def test_transverter_pa_boost_draws_from_battery_not_3v3():
    t = solve_tree([Load("PA", "XV_5V", 0.11)], 3.6)
    assert t.convs["U_XV_BOOST"].v_in == 3.6
    assert t.convs["U_BOOST"].mode == "off"


def test_aon_ldo_dropout_is_not_a_failure_while_wba_has_headroom():
    t = solve_tree([Load("WBA", "3V3_AON", 0.01)], 3.4)
    assert t.convs["U_AON_LDO"].mode == "dropout" and not t.flags()


def test_fresh_pack_runs_ready_hold_and_reports_descent_limit():
    r = run_mission(PACK_3X_1520HPM, build_profile(shelf_years=0.0, descent_s=10.0))
    ready = next(p for p in r.phases if p.phase.name == "ready hold")
    assert not ready.fail and 100 < ready.q_end_mah < 200
    s, r2 = max_descent_s(PACK_3X_1520HPM, dict(shelf_years=0.0), 22.0, 22.0)
    assert s >= 0 or first_failure(r2)


def test_cutter_load_scales_with_sectors():
    assert L.cutter(2).amps == pytest.approx(2 * L.cutter(1).amps)


def test_radar_1v8_buck_draws_less_than_the_ldo():
    from smash.sim.battery.power_tree import converters
    ld = [Load("radar 1.8 V idle", "AWR_1V8", 0.03)]
    ldo = solve_tree(ld, 3.7, convs=converters())
    buck = solve_tree(ld, 3.7, convs=converters(radar_1v8_buck=True))
    assert buck.i_bat < 0.6 * ldo.i_bat


def test_comp_boost_variant_raises_the_switch_limit():
    from smash.sim.battery.power_tree import converters
    c = {x.ref: x for x in converters(comp_boost="B")}["U_COMP_BOOST"]
    assert c.i_sw_max_a == 8.0 and c.vin_min < 2.9
