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
  C2 "arc_al_two"   C without the middle arc (S2): S1 + S3, 15 mm apart —
                    in C, S2 sat 5–10 mm from both and coupled at −6…−9 dB
                    (2026-11-16 local-skin run).
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


def _arc(name, f_ghz, angle, z, arc_dir, *, eps=EPS_EFF, width=1.5, scale=1.0,
         feed=6.0, end_len=0.0, end_dz=0.0):
    L = half_wave_slot_mm(f_ghz, eps) * scale
    return Slot(name, "arc", angle, z, arc_dir * L, width=width, feed_offset=feed,
                f_design_ghz=f_ghz, end_len=end_len, end_dz=end_dz)


# Per-slot overrides (2026-11-17), passed as --set S3_scale=0.89 etc.:
#   S<n>_scale  length multiplier on the half-wave length
#   S<n>_feed   feed distance from the slot's START end [mm]
#   S<n>_dir    +1 runs from 107° upward, -1 from 253° downward (mirrored —
#               keeps the two feeds, and so their castellations, apart)
#   S<n>_gap    lower board of the gap the slot sits in (e.g. "wakeup_board"
#               puts it in the wakeup↔power gap, next to the radio board)
#   S<n>_f      design frequency [GHz]; for S4/S5 (C2 only) it CREATES the
#               extra slot (high-band / transverter slots, 2026-11-17)
#   S<n>_width  slot width [mm] (wider = more bandwidth)
#   S<n>_angle  start angle [deg] instead of the sector edge
#   S<n>_off    1 removes the slot (2026-11-17: S3 merged into S1)
#   S<n>_dz     axial offset [mm] from the gap mid-height, negative = down
#               (2026-11-21, user: move the slots down within / past the gap)
#   S<n>_endlen axial end bars across both ends of an arc slot, total length
#               [mm] (H / dog-bone): lowers the resonance without more angle
#   S<n>_enddz  end-bar centre offset from the slot centre [mm], + = up
#               (enddz = (endlen - width) / 2 gives bars running up only)
SLOT_OVERRIDE_KEYS = ("scale", "feed", "dir", "gap", "f", "width", "angle", "off", "dz", "endlen", "enddz")
EXTRA_SLOTS = ("S4", "S5")


def _split_slot_overrides(kw: dict) -> tuple[dict, dict]:
    ov, rest = {}, {}
    for k, v in kw.items():
        name, _, key = k.partition("_")
        if name[:1] == "S" and name[1:].isdigit() and key in SLOT_OVERRIDE_KEYS:
            ov.setdefault(name, {})[key] = v
        else:
            rest[k] = v
    return ov, rest


def _next_board(lo):
    order = sorted(BOARD_MID_Z_MM, key=BOARD_MID_Z_MM.get)
    return order[order.index(lo) + 1]


def _c_arc(name, f_ghz, z, ov):
    o = ov.get(name, {})
    if "gap" in o:
        z = _gap_mid(o["gap"], _next_board(o["gap"]))
    z += float(o.get("dz", 0.0))
    f_ghz = float(o.get("f", f_ghz))
    d = int(o.get("dir", +1))
    angle = ANTENNA_SECTOR_FREE[0] + 2.0 if d > 0 else ANTENNA_SECTOR_FREE[1] - 2.0
    angle = float(o.get("angle", angle))
    return _arc(name, f_ghz, angle, z, d, scale=float(o.get("scale", 1.0)),
                feed=float(o.get("feed", 6.0)), width=float(o.get("width", 1.5)),
                end_len=float(o.get("endlen", 0.0)), end_dz=float(o.get("enddz", 0.0)))


def _gap_mid(lo, hi):
    return 0.5 * (BOARD_MID_Z_MM[lo] + BOARD_MID_Z_MM[hi])


def option_slots(option: str, overrides: dict | None = None) -> list:
    ov = overrides or {}
    if option == "A":      # cells at 70/190/310° → gaps 10/130/250°
        return [_axial("S1", 2.2, 130.0), _axial("S2", 2.3, 180.0), _axial("S3", 2.4, 230.0)]
    if option == "B":
        # S1: 40 mm down at 130° then +55° round (to ~185°) at z≈6.6;
        # S2: 35 mm down at 200° then −48° round (to ~152°) at z≈11.6 —
        # the two arcs sit 5 mm apart axially, clear of each other's legs.
        return [_folded("S1", 1.75, 130.0, 40.0, +1), _folded("S2", 2.0, 200.0, 35.0, -1),
                _axial("S3", 2.4, 230.0)]
    if option == "C":      # arcs inside the 105–255° sector, one per board gap
        # (2026-11-21) fin_ble merged into activation: S1's default gap is
        # the one above activation (product: S1_gap=wakeup_board).
        return [_c_arc("S1", 2.15, _gap_mid("activation_interface", "wakeup_board"), ov),
                _c_arc("S2", 2.3, _gap_mid("wakeup_board", "power_board"), ov),
                _c_arc("S3", 2.45, _gap_mid("power_board", "companion_compute"), ov)]
    if option == "C2":     # C's S1 + S3 unchanged, no S2 (+ optional S4/S5)
        out = [s for s in option_slots("C", ov) if s.name != "S2"
               and not ov.get(s.name, {}).get("off")]
        for name in EXTRA_SLOTS:
            o = ov.get(name, {})
            if "f" in o:
                if "gap" not in o:
                    raise ValueError(f"{name} needs {name}_gap (lower board of its gap)")
                out.append(_c_arc(name, float(o["f"]), 0.0, ov))
        return out
    raise KeyError(option)


def option_model(option: str, **kw):
    """Tower + slots for option A/B/C/C2; keyword overrides go to build_tower,
    except S<n>_scale / S<n>_feed / S<n>_dir (per-slot, C and C2 only)."""
    ov, kw = _split_slot_overrides(kw)
    if ov and option not in ("C", "C2"):
        raise ValueError(f"slot overrides {sorted(ov)} only apply to options C / C2")
    base = dict(boards=CORE_BOARDS, slots=option_slots(option, ov), potting="potting_black",
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
