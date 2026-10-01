"""No Cu coins remain — and the coin-lowering machinery stays sane.

radar_module + companion_compute coins were REMOVED 2026-07-04 (coin audit:
net-negative in the real potted stack — see project_companion_coin_sweep
memory). The last coin — cell_floor_board's compression plate — went with
that tile on 2026-07-30, when the side-solder-tab cells started standing
directly on aft_end_board. `_lower_coins_for_top_routing` (drop a coin's top
face below the top N copper layers so F.Cu + In1…In(N-1) stay routable) is
kept live for any future coin restoration; this locks both facts.
"""
from __future__ import annotations

from smash.layout.boards.smash_evb_v1 import (
    build_panel,
    N_TOP_ROUTABLE_LAYERS,
    _lower_coins_for_top_routing,
    _nth_copper_bottom_z,
)
from smash.state import Board, CuCoinInsert


def test_no_coined_boards_remain():
    _panel, boards = build_panel()
    coined = [b.name for b in boards.values()
              if (getattr(b, "cu_coin_inserts", None) or [])]
    assert coined == []


def test_lowering_machinery_still_works_on_a_synthetic_coin():
    """Attach a full-height coin to a synthetic 20L tile and check the
    lowering pass still frees the top N copper layers (the restoration
    path documented in smash_evb_v1's coin note)."""
    b = Board("synthetic_coined", copper_layers=20)
    b.set_fitted_stackup()
    b.cu_coin_inserts = [CuCoinInsert(
        position_mm=(0.0, 0.0), length_mm=20.0, width_mm=20.0,
        ladder_length_mm=16.0, ladder_width_mm=16.0,
        thickness_mm=3.0, flange_thickness_mm=0.5,
        z_top_mm=3.15, corner_chamfer_radius_mm=5.0, kind="T")]
    _lower_coins_for_top_routing({"synthetic_coined": b})
    z_cap = _nth_copper_bottom_z(b, N_TOP_ROUTABLE_LAYERS)
    assert z_cap is not None
    c = b.cu_coin_inserts[0]
    assert c.z_top_mm <= z_cap + 1e-6          # top N coppers stay routable
    assert (c.z_top_mm - c.thickness_mm) < 0.3  # bottom face kept near B.Cu
