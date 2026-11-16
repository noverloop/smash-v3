"""The model ladder and the three slot options the user asked to compare
(2026-11-16, "simulate all first").

Geometry facts the options are built around (sleeve unroll): the tower is
~47 mm (core / qpd / camera; ~54 mm with radar), the radio feeds sit on
wakeup at z ≈ 36.2 mm, the aluminium battery holder fills z ≈ 1.3–24.9 mm.
A straight axial slot can use at most ~45 mm (aft_end top → compute top), so
half-wave slots below ~2.2 GHz must fold. Feeds are offset from a slot END
to the wakeup level (the castellation feed), which also lands the input
impedance near 50 Ω (a slot's impedance falls towards its ends).

  A "axial_raised"  composite holder, cells turned so two inter-cell gaps
                    face the antenna sector; three straight axial slots,
                    band raised to ≈2.2 / 2.3 / 2.4 GHz.
  B "axial_folded"  composite holder; S3 straight; S1 (1.75 GHz) and
                    S2 (2.0 GHz) L-shaped (axial + arc).
  C "arc_al"        aluminium holder kept; three ARC slots round the sleeve
                    in the clear zone (activation → compute), one per
                    inter-board gap; rings cut away in the antenna sector.
"""
from __future__ import annotations

from smash.sim.antenna.geometry import (BOARD_MID_Z_MM, BOARD_T_MM, CORE_BOARDS,
                                        Slot, build_tower, half_wave_slot_mm)

EPS_EFF = 2.25          # air outside / potting + LCP inside — first guess, tuned by M1
Z_FEED = BOARD_MID_Z_MM["wakeup_board"]
Z_TOP = BOARD_MID_Z_MM["companion_compute"] + BOARD_T_MM / 2 - 0.5
ANTENNA_SECTOR_FREE = (105.0, 255.0)


def _axial(name, f_ghz, angle, *, eps=EPS_EFF, width=1.5):
    L = half_wave_slot_mm(f_ghz, eps)
    return Slot(name, "axial", angle, Z_TOP, -L, width=width,
                feed_offset=Z_TOP - Z_FEED, f_design_ghz=f_ghz)


def _folded(name, f_ghz, angle, axial_mm, arc_dir, *, eps=EPS_EFF, width=1.5):
    L = half_wave_slot_mm(f_ghz, eps)
    return Slot(name, "L", angle, Z_TOP, -axial_mm, width=width,
                feed_offset=Z_TOP - Z_FEED, arc_length=arc_dir * max(L - axial_mm, 0.0),
                f_design_ghz=f_ghz)


def _arc(name, f_ghz, angle, z, arc_dir, *, eps=EPS_EFF, width=1.5):
    L = half_wave_slot_mm(f_ghz, eps)
    return Slot(name, "arc", angle, z, arc_dir * L, width=width, feed_offset=6.0,
                f_design_ghz=f_ghz)


def _gap_mid(lo, hi):
    return 0.5 * (BOARD_MID_Z_MM[lo] + BOARD_MID_Z_MM[hi])


def option_slots(option: str) -> list:
    if option == "A":      # cells at 70/190/310° → gaps 10/130/250°
        return [_axial("S1", 2.2, 130.0), _axial("S2", 2.3, 180.0), _axial("S3", 2.4, 230.0)]
    if option == "B":
        # S1: 40 mm down at 130° then +55° round (to ~185°) at z≈6.6;
        # S2: 35 mm down at 200° then −48° round (to ~152°) at z≈11.6 —
        # the two arcs sit 5 mm apart axially, clear of each other's legs.
        return [_folded("S1", 1.75, 130.0, 40.0, +1), _folded("S2", 2.0, 200.0, 35.0, -1),
                _axial("S3", 2.4, 230.0)]
    if option == "C":      # arcs inside the 105–255° sector, one per board gap
        return [_arc("S1", 2.15, 107.0, _gap_mid("activation_interface", "fin_ble_board"), +1),
                _arc("S2", 2.3, 107.0, _gap_mid("wakeup_board", "power_board"), +1),
                _arc("S3", 2.45, 107.0, _gap_mid("power_board", "companion_compute"), +1)]
    raise KeyError(option)


def option_model(option: str, **kw):
    """Tower + slots for option A/B/C; keyword overrides go to build_tower."""
    base = dict(boards=CORE_BOARDS, slots=option_slots(option), potting="potting_black",
                rings="al", ring_free_sector=ANTENNA_SECTOR_FREE, keepout_depth_mm=4.0)
    if option in ("A", "B"):
        base.update(holder="composite", cell_rot_deg=70.0)
    else:
        base.update(holder="al", cell_rot_deg=90.0)
    base.update(kw)
    return build_tower(**base)


# M2/M3/M5 sweeps (parameter name → values) applied to each option.
SWEEPS = {
    "keepout_depth_mm": (0.0, 2.0, 4.0, 6.0),
    "rings": ("al_cut", "al", "peek"),
    "potting": ("potting_black", "potting_rf"),
    "coating_mm": (0.0, 0.3),
}
