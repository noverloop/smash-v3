"""Board-edge castellations — the side-wall interconnect contract.

Replaces the LGA land fields (2026-11-14 architecture: potted, spacer-less
tower inside an injection-moulded LDS sleeve). Every net that runs between
two or more rigid snake boards gets one or more **lanes**: a fixed PHYSICAL
angle around the Ø34 stack axis. On every board the net touches, a plated
half-hole (castellation) sits on the board outline at that angle; the
sleeve's LDS trace runs axially at the same angle and lands on each
castellation through a plated via (solder / conductive adhesive). Boards in
between that do NOT carry the net have no castellation at that angle, so
lanes can be re-used by nets whose board spans don't overlap.

Physical vs board-local angle: rigid boards all sit upright in the stack;
the nose-ward group (power_board onward) is turned 180° about the stack axis
(`board_fold_transforms`). Lanes are assigned in the physical frame
(aft_end_board) and mapped into each board's local frame, so a lane is ONE
straight line on the finished cylinder.

Contract: `castellation_contract()` returns a dict that config builds replay
verbatim (economies of scale — the same board fabs identically in every
config). Nets absent from a config still get their pad (unconnected).
"""
from __future__ import annotations

import math
import sys

from smash.state import Pin, Pad, Footprint

CAST_PITCH_MM = 0.8            # lane pitch at the rim (sleeve via outer opening ~0.55 mm)
CAST_DRILL_MM = 0.45           # plated half-hole drill, centred on the outline
CAST_PAD_MM = 0.65             # copper annulus Ø on the board faces (tented)
# (2026-11-14) Sector layout of the sleeve, PHYSICAL angles:
#   • SIGNAL sector centred on 0° (±105° = 210°): every signal / power lane,
#     on the sleeve's OUTER face, joined to its castellation by a via.
#   • ANTENNA sector opposite (105° … 255°, 150°): no lanes. The sleeve's
#     INNER face carries a GND plane there (joined to fixed GND castellations
#     through the same kind of vias) = the antennas' ground; antenna copper
#     on the OUTER face.
#   • The two half-shell SEAMS (a planar split → diametrically opposite):
#     105° (the sector edge) and 285° (inside the signal sector, as a narrow
#     lane-free stripe). The potting feed / vent grooves run along the seams.
SIGNAL_SECTOR_CENTRE_DEG = 0.0
SIGNAL_SECTOR_HALF_DEG = 105.0
SEAM_ANGLES_DEG = (105.0, 285.0)
SEAM_HALF_WIDTH_DEG = 4.0
RESERVED_SECTORS_DEG = tuple((a, SEAM_HALF_WIDTH_DEG) for a in SEAM_ANGLES_DEG)
# GND: no lanes — fixed castellations in the antenna sector, near its edges
# (antenna centre stays free), on every rigid board, tied to the inner plane.
GND_CAST_ANGLES_DEG = (113.0, 120.0, 240.0, 247.0)
# Antenna feeds: single-board nets that leave fin_ble_board through a
# castellation + sleeve via to the antenna copper on the sleeve's outer face.
ANTENNA_FEED_ANGLES_DEG = {"ANT_2G4_FEED": 135.0, "ANT_SUBG_FEED": 205.0}
# Restraint (33 V) circuit leaves the stack at the plug ring: ACTIVATE_HV is
# already a lane; the switched return PARACHUTE_CUTTER_ACTIVATE lives only on
# the aft board, so it gets an EXIT lane (aft board → ring).
PLUG_EXIT_NETS = ("PARACHUTE_CUTTER_ACTIVATE",)
RESTRAINT_NETS = ("ACTIVATE_HV", "PARACHUTE_CUTTER_ACTIVATE")
POWER_LANE_WIDTH_MM = 0.6      # one WIDE (electroplated) lane per power rail
SIGNAL_LANE_WIDTH_MM = 0.2
MANF_PN = "CASTELLATIONS"


def _is_gnd(net) -> bool:
    names = {net.name, *(getattr(net, "aliases", None) or [])}
    return bool(names & {"GND", "FLEX_GND"})


def _mult(net) -> int:
    """One lane per net: power rails get a WIDE lane instead of extra ones."""
    return 1


def _in_signal_sector(ang: float) -> bool:
    d = (ang - SIGNAL_SECTOR_CENTRE_DEG + 180.0) % 360.0 - 180.0
    return abs(d) <= SIGNAL_SECTOR_HALF_DEG - SEAM_HALF_WIDTH_DEG


def board_fold_transforms(panel, chain) -> dict:
    """{cell_name: 2×2 matrix M} with local = M · physical (physical = the
    aft_end_board / chain[0] frame). Matches the stack assembly's pose
    (`smash.export.stackup_step._tile_pose`): the backbone is an interposer
    STACK, not an accordion — every rigid board sits upright in the same
    orientation, except the nose-ward group (`cavities.is_rotated_180`,
    power_board onward), which is turned 180° about the stack axis. (A
    per-fold mirror would wrongly flip every board after an even run of
    spacers, e.g. the battery column.)"""
    from smash.layout.cavities import is_rotated_180
    chain = list(chain)
    return {n: (((-1, 0), (0, -1)) if is_rotated_180(chain, n)
                else ((1, 0), (0, 1)))
            for n in chain}


def _local_xy(M, phys_deg: float, r: float) -> tuple:
    a = math.radians(phys_deg)
    vx, vy = math.cos(a), math.sin(a)
    (m11, m12), (m21, m22) = M
    return (round(r * (m11 * vx + m12 * vy), 4),
            round(r * (m21 * vx + m22 * vy), 4))


def _lane_angles(r: float) -> list:
    step = math.degrees(CAST_PITCH_MM / r)
    n = int(360.0 // step)
    step = 360.0 / n                       # close the circle evenly
    out = []
    for k in range(n):
        ang = k * step
        if not _in_signal_sector(ang):
            continue
        if any(min(abs(ang - c), 360 - abs(ang - c)) < hw
               for c, hw in RESERVED_SECTORS_DEG):
            continue
        out.append(round(ang, 3))
    # fill from the sector centre outward, so lanes cluster round 0°
    out.sort(key=lambda a: min(abs(a - SIGNAL_SECTOR_CENTRE_DEG),
                               360 - abs(a - SIGNAL_SECTOR_CENTRE_DEG)))
    return out


def castellation_contract(design, panel, boards) -> dict:
    """Compute the lane contract for this (maximalist) build."""
    from smash.parts.connectors import is_off_backbone
    chain = [n for n in (panel.snake_chain or []) if n in boards]
    rigid = [n for n in chain if not getattr(boards[n], "is_spacer", False)
             and getattr(boards[n], "kind", "rigid") != "flex"]
    pos = {n: i for i, n in enumerate(rigid)}
    # Branch leaves (qpd / camera on their flex) are reached THROUGH their
    # parent tile, so their pins count as the parent's for lane spans.
    parent = {dst: src for src, dst in (getattr(panel, "branches", None) or [])}

    def host(b):
        seen = set()
        while b in parent and b not in seen:
            seen.add(b)
            b = parent[b]
        return b
    tag = {c.ref: host(getattr(c, "board_tag", None)) for c in design.chips
           if getattr(c, "manf_pn", None) not in ("LGA_lands", MANF_PN)}
    r = 17.0
    g = boards[rigid[0]].geometry if rigid else None
    if g is not None and getattr(g, "outline_radius_mm", None):
        r = g.outline_radius_mm
    angles = _lane_angles(r)
    occupied = {a: [] for a in angles}     # angle → [(lo, hi)]
    lanes: dict = {}

    def free(a, lo, hi):
        return all(hi < l or lo > h for l, h in occupied[a])

    # GND: fixed castellations in the antenna sector on every board, tied
    # together by the sleeve's inner GND plane (not by outer lanes).
    gnd = next((n for n in design.nets if _is_gnd(n)), None)
    if gnd is not None and len(rigid) >= 2:
        lanes[gnd.name] = {"angles": list(GND_CAST_ANGLES_DEG),
                           "boards": list(rigid), "kind": "gnd_plane"}
    # Antenna feeds: fin_ble only, at fixed antenna-sector angles.
    feeds = {}
    for fname, fang in ANTENNA_FEED_ANGLES_DEG.items():
        if design.net_by_name(fname) is not None and "fin_ble_board" in rigid:
            feeds[fname] = {"angles": [fang], "boards": ["fin_ble_board"],
                            "kind": "antenna_feed"}

    todo = []
    for net in design.nets:
        if gnd is not None and net is gnd:
            continue
        if is_off_backbone(net.name):
            continue
        bset = {tag.get(rf) for rf, _p in net.pins} & set(rigid)
        if len(bset) < 2:
            continue
        idx = sorted(pos[b] for b in bset)
        todo.append((idx[0], idx[-1], net, sorted(bset, key=pos.get)))
    # Longest spans first, then by start — first-fit over the angle ring.
    todo.sort(key=lambda t: (-(t[1] - t[0]), t[0], t[2].name))
    overflow = []
    for lo, hi, net, bset in todo:
        need, got = _mult(net), []
        for a in angles:
            if len(got) == need:
                break
            if free(a, lo, hi):
                occupied[a].append((lo, hi))
                got.append(a)
        if len(got) < need:
            overflow.append(net.name)
        if got:
            lanes[net.name] = {"angles": got, "boards": bset,
                               "kind": "power" if getattr(net, "kind", None) == "power"
                               else "signal",
                               "width_mm": (POWER_LANE_WIDTH_MM
                                            if getattr(net, "kind", None) == "power"
                                            else SIGNAL_LANE_WIDTH_MM)}
    for en in PLUG_EXIT_NETS:
        if en in lanes or design.net_by_name(en) is None or not rigid:
            continue
        hv = lanes.get("ACTIVATE_HV", {}).get("angles", [])
        cand = sorted((a for a in angles if free(a, 0, 0)),
                      key=lambda a: min(abs(a - hv[0]), 360 - abs(a - hv[0])) if hv else 0)
        if cand:
            occupied[cand[0]].append((0, 0))
            lanes[en] = {"angles": [cand[0]], "boards": [rigid[0]],
                         "kind": "plug_exit", "width_mm": POWER_LANE_WIDTH_MM}
    used = sum(1 for a in angles if occupied[a])
    lanes.update(feeds)
    if overflow:
        print(f"  WARNING: castellations: {len(overflow)} net(s) short of "
              f"lanes: {', '.join(overflow[:10])}", file=sys.stderr)
    return {"pitch_mm": CAST_PITCH_MM, "radius_mm": r,
            "n_angles": len(angles), "n_used": used,
            "reserved_deg": [list(s) for s in RESERVED_SECTORS_DEG],
            "signal_sector_deg": [SIGNAL_SECTOR_CENTRE_DEG - SIGNAL_SECTOR_HALF_DEG,
                                  SIGNAL_SECTOR_CENTRE_DEG + SIGNAL_SECTOR_HALF_DEG],
            "seam_deg": list(SEAM_ANGLES_DEG),
            "lanes": lanes}


def place_castellations(design, panel, boards, *, connect,
                        contract: dict | None = None) -> tuple:
    """Emit one CASTELLATIONS chip per rigid snake board (pads on the outline
    at the contract's lanes, mapped into the board's folded frame). Computes
    the contract when none is given. Returns (contract, {board: n_pads})."""
    from smash.state.topology.placement import Placement
    if contract is None:
        contract = castellation_contract(design, panel, boards)
    chain = [n for n in (panel.snake_chain or []) if n in boards]
    M = board_fold_transforms(panel, chain)
    r = contract["radius_mm"]
    per_board: dict = {}
    for net_name, lane in contract["lanes"].items():
        for b in lane["boards"]:
            if b in boards and b in M:
                for a in lane["angles"]:
                    per_board.setdefault(b, []).append((a, net_name))
    counts = {}
    for b, items in per_board.items():
        items.sort()
        pads = []
        for i, (a, _n) in enumerate(items):
            pads.append(Pad(num=str(i + 1), position_mm=_local_xy(M[b], a, r),
                            size_mm=(CAST_PAD_MM, CAST_PAD_MM), shape="round",
                            layer="*.Cu", drill_mm=CAST_DRILL_MM, paste=False,
                            # Face annulus TENTED by solder mask: the sleeve
                            # via's joint goes into the plated half-barrel at
                            # the edge (never masked), so the face copper is
                            # not needed — and the Al battery ring bears on
                            # cell_floor's top / fin_ble's bottom right over
                            # it (mask + anodise = double insulation).
                            solder_mask_expansion_mm=-CAST_PAD_MM / 2.0,
                            note="castellated"))
        fp = Footprint(name=f"Castellations_{b}",
                       package_class="board-edge castellations",
                       pads=pads, size_mm=(2 * r, 2 * r), height_mm=0.0,
                       source="project")
        chip = design.add_chip(
            ref=f"J_CAST_{b}", board_tag=b, manf="project",
            manf_pn=MANF_PN, name=MANF_PN, footprint=fp,
            pins=[Pin(num=p.num, name=f"{items[k][1]}@{items[k][0]:g}deg")
                  for k, p in enumerate(pads)],
            weight_g=0.0, height_mm=0.0,
            note=("plated half-holes on the board outline; each lane is a "
                  "fixed physical angle on the stack — the LDS sleeve's via "
                  "lands here"))
        for k, (_a, net_name) in enumerate(items):
            if design.net_by_name(net_name) is not None or any(
                    net_name in (n.aliases or []) for n in design.nets):
                connect(net_name, chip.pin(str(k + 1)))
        boards[b].chip_placements.append(Placement(
            position_mm=(0.0, 0.0), rotation_deg=0.0, item=chip,
            face="top", locked=True))
        counts[b] = len(pads)
    return contract, counts
