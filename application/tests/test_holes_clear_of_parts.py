"""(2026-11-20) No part — packed OR locked — may cover a drilled hole (potting
holes, payload stops, aft-cap screws). Locks bypass the packer's keepouts, so
three locked parts had drifted over potting holes (radar D_IR_WAKE, compute
U_NAND_B, power R_USBOR_USB_L)."""
from __future__ import annotations

import importlib
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_no_part_over_a_hole():
    from shapely.geometry import Point, box
    sys.path.insert(0, str(REPO))
    try:
        gen = importlib.import_module("generate_stackup")
    finally:
        sys.path.pop(0)
    from smash.layout.placer import place_design
    from smash.layout.placer.grid import placement_rects_mm
    d = gen.Design()
    gen._prime_power_rails(d)
    for fn in gen._BOARD_BUILDERS.values():
        fn(d)
    gen._empty_aft_end_top(d)
    panel, boards = gen.build_panel(straight=gen._STRAIGHT_SNAKE,
                                    battery_length_mm=gen._compartment_mm())
    gen.build_spacers(d, boards)
    gen._mark_preplace_keepouts(d, boards)
    gen._mark_ring_band_keepouts(panel, boards)
    place_design(d, panel, boards)
    bad = []
    for name, b in boards.items():
        g = getattr(b, "geometry", None)
        if g is None or b.is_spacer:
            continue
        for h in g.holes:
            hole = Point(*h.position_mm).buffer(h.diameter_mm / 2 + 0.2)
            for pl in b.chip_placements:
                c = pl.item
                if getattr(c, "manf_pn", "") in ("CASTELLATIONS", "LGA_lands"):
                    continue
                if c.footprint is None:
                    continue
                # (2026-11-21) the TRUE occupied outline (a 45°-turned part —
                # the radar AoP — is a staircase, not its 24 mm bounding square)
                rects = placement_rects_mm(pl, c.footprint)
                if any(box(*r).intersects(hole) for r in rects):
                    bad.append(f"{name}: {c.ref} ({pl.face}{', locked' if pl.locked else ''}) "
                               f"over {h.tag} hole at {h.position_mm}")
    assert not bad, "\n".join(bad)
