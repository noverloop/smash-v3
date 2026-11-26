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

import dataclasses
import math
import sys

from smash.state import Pin, Pad, Footprint

CAST_PITCH_MM = 0.8            # lane pitch at the rim (sleeve via outer opening ~0.55 mm)
# Plated half-holes at PCBWay's NORMAL process (capabilities: castellated hole
# ≥ 0.5 mm, edge-to-edge ≥ 0.3 mm): 0.50 mm at 0.8 mm pitch = 0.30 mm between
# holes; the Ø0.70 pad keeps a 0.10 mm ring and 0.10 mm copper to its neighbour.
CAST_DRILL_MM = 0.50           # plated half-hole drill, centred on the outline
CAST_PAD_MM = 0.70             # copper annulus Ø on the board faces (tented)
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
# GND: no lanes — fixed castellations in the antenna sector on every rigid
# board. (2026-11-17) One PAIR per slot antenna, flanking its feed in the
# middle of the CPW ground bands (smash.parts.antenna_slots): they bond the
# slot patch / CPW grounds to the boards (the sim's grounded feed).
from smash.parts.antenna_slots import SLOTS as _ANT_SLOTS
GND_CAST_ANGLES_DEG = tuple(sorted(a for s_ in _ANT_SLOTS for a in s_.gnd_flank_deg))
# Antenna feeds: single-board nets that leave the RADIO board (the board
# their chips sit on — wakeup since 2026-11-16) through a castellation +
# sleeve via to the sleeve's antenna copper. (2026-11-17) Two DEDICATED
# printed slots, no RF switching: S1 (LR2021, 2.1-2.48 GHz) and S3 (BLE).
# Sub-GHz (RF_LF_EXT) and slot S2 are gone. (2026-11-17) Angles = the CPW
# strip centres of the simulated slots (antenna_slots.SLOTS); S4 carries the
# 4.4-5.0 GHz transverter since 2026-11-18. A feed whose net is absent from
# the design (e.g. a config without the wakeup radio) gets no castellation.
ANTENNA_FEED_ANGLES_DEG = {s_.net: round(s_.feed_deg, 1) for s_ in _ANT_SLOTS}
# Plug ring (2026-11-14): the aft board's bottom-face bench/harness interface
# (SPI, FIN 1-4, CAN, BAT, PARACHUTE WIRES, …) is UNCHANGED — it is now reached
# on the sleeve's plug ring instead of on the board face. Each interface pad
# gets an EXIT castellation on the aft board (any free angle, both sectors),
# allocated in group order so each group stays contiguous round the ring.
# Guarded buses (2026-11-15): nets that cross as ONE contiguous block of
# lanes interleaved with GND guard lanes (G S G S … G) over the bus span —
# a coplanar-ish return path right next to every line on the sleeve's
# outer face. key → (nets in order, guard lane key). The LR2021 SPI +
# control crossing from the WBA55 (wakeup) to the radio (fin_ble).
# (2026-11-16) Empty: the LR2021 moved next to its WBA host on wakeup, so its
# SPI + control lines are board-local. The mechanism stays for future buses.
GUARDED_BUSES: dict = {}
# Lane re-use policy (2026-11-18, layout-EE input). "reuse": an angle carries
# several nets whose board spans don't overlap (vertical lines re-allocated
# where empty). "dedicated": ONE angle per signal over the full stack height —
# simpler to route / inspect, but costs angles; `lane_budget` reports both.
# Nose payloads (radar in the snake, QPD / camera via cone exits) all land on
# companion_compute at FIXED angles in the maximalist contract, which every
# config replays — so compute fabs identically whichever cup is fitted.
LANE_POLICY = "reuse"
# Lanes from wakeup upward may use the antenna sector (both slot antennas sit
# below wakeup). Off since the crown moved onto compute's top-face pads
# (2026-11-18): the signal sector has room again.
# (2026-11-21) ON again: fixed noses put ~45 payload nets on lanes from compute
# up; the antenna sector is free above the slots' copper (see lo_upper).
UPPER_ANTENNA_LANES = True
POWER_LANE_WIDTH_MM = 0.6      # one WIDE (electroplated) lane per power rail
SIGNAL_LANE_WIDTH_MM = 0.2
MANF_PN = "CASTELLATIONS"


def _is_gnd(net) -> bool:
    names = {net.name, *(getattr(net, "aliases", None) or [])}
    return bool(names & {"GND", "FLEX_GND"})


def _mult(net) -> int:
    """One lane per net: power rails get a WIDE lane instead of extra ones."""
    return 1


def _ring_angles(r: float) -> list:
    """Every lane slot round the full ring (same grid as `_lane_angles`),
    minus the seam stripes, ascending from the 105° seam."""
    step = math.degrees(CAST_PITCH_MM / r)
    n = int(360.0 // step)
    step = 360.0 / n
    out = [round(k * step, 3) for k in range(n)
           if not any(min(abs(k * step - c), 360 - abs(k * step - c)) < hw
                      for c, hw in RESERVED_SECTORS_DEG)]
    return sorted(out, key=lambda a: (a - SEAM_ANGLES_DEG[0]) % 360.0)


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


def castellation_contract(design, panel, boards, plug_groups=None,
                          cone_exits=None, lane_policy: str | None = None,
                          quiet: bool = False) -> dict:
    """Compute the lane contract for this (maximalist) build. `lane_policy`
    overrides LANE_POLICY ("reuse" | "dedicated")."""
    policy = lane_policy or LANE_POLICY
    if policy not in ("reuse", "dedicated"):
        raise ValueError(f"unknown lane_policy {policy!r}")
    from smash.parts.connectors import is_off_backbone
    from smash.export import nose_interface as NI
    chain = [n for n in (panel.snake_chain or []) if n in boards]
    # (2026-11-18) Nose modules (radar / QPD / camera / USB) are separate
    # cones on the standard CROWN: electrically they hang off compute, their
    # nets leave the core sleeve only through the crown (nose_interface).
    crown_host = NI.HOST if (NI.MODULAR and NI.HOST in chain) else None
    payloads = [b for b in NI.PAYLOAD_BOARDS if b in boards] if crown_host else []
    rigid = [n for n in chain if not getattr(boards[n], "is_spacer", False)
             and getattr(boards[n], "kind", "rigid") != "flex"
             and n not in payloads]
    pos = {n: i for i, n in enumerate(rigid)}
    # Branch leaves (qpd / camera on their flex) are reached THROUGH their
    # parent tile, so their pins count as the parent's for lane spans.
    parent = {dst: src for src, dst in (getattr(panel, "branches", None) or [])}
    # Nose leaves are electrically compute leaves whatever panel edge they
    # hang from (the USB nose hangs off the radar tail in the maximalist panel).
    for src, leaf, _nets in (cone_exits or []):
        parent[leaf] = src
    for pb in payloads:
        parent[pb] = crown_host
    nose_tile = None
    if not NI.MODULAR:
        # (2026-11-21) fixed noses: whichever payload a config carries sits in
        # the NOSE SLOT above compute — in the superset that is the payload
        # tile on the chain; the others (branch leaves here) share its lanes.
        nose_tile = next((n for n in chain if n in NI.PAYLOAD_BOARDS), None)
        for pb in NI.PAYLOAD_BOARDS:
            if nose_tile and pb != nose_tile:
                parent[pb] = nose_tile
    # (2026-11-19) aft_end_cap contacts (virtual board): allocated as if on the
    # aft board, so their lanes run all the way down to the aft rim.
    if rigid:
        parent[AFT_CAP_TAG] = rigid[0]

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
    # (2026-11-18) ANTENNA-sector angles open to lanes that start at the
    # wakeup board or above: both slot antennas (S1, S4) sit below wakeup, so
    # the sector above it is free copper-wise — needed once the nose crown
    # reserves compute pads under its teeth. GND / feed castellations stay clear.
    _half = 0.5 * math.degrees(CAST_PITCH_MM / r)
    _fixed = list(GND_CAST_ANGLES_DEG) + list(ANTENNA_FEED_ANGLES_DEG.values())
    # (2026-11-21) keep the compute KEY notch (sleeve index rib) clear: its
    # half-width + a castellation pad + 0.2 mm (it sat on RADAR_EN's pad).
    _key_half = math.degrees((NI.KEY_W_MM / 2 + CAST_PAD_MM / 2 + 0.2) / r)
    upper_angles = ([a for a in _ring_angles(r) if not _in_signal_sector(a)
                     and all(min(abs(a - f), 360 - abs(a - f)) > 2 * _half for f in _fixed)
                     and min(abs(a - NI.KEY_ANGLE_DEG), 360 - abs(a - NI.KEY_ANGLE_DEG)) > _key_half]
                    if UPPER_ANTENNA_LANES else [])
    occupied = {a: [] for a in angles + upper_angles}     # angle → [(lo, hi)]
    lanes: dict = {}

    def free(a, lo, hi):
        if policy == "dedicated":
            return not occupied[a]
        return all(hi < l or lo > h for l, h in occupied[a])

    # GND: fixed castellations in the antenna sector on every board, tied
    # together by the sleeve's inner GND plane (not by outer lanes).
    gnd = next((n for n in design.nets if _is_gnd(n)), None)
    if gnd is not None and len(rigid) >= 2:
        lanes[gnd.name] = {"angles": list(GND_CAST_ANGLES_DEG),
                           "boards": list(rigid), "kind": "gnd_plane"}
    # Antenna feeds: on the radio board (wakeup), at fixed antenna-sector angles.
    feeds = {}
    for fname, fang in ANTENNA_FEED_ANGLES_DEG.items():
        fnet = design.net_by_name(fname)
        if fnet is None:
            continue
        fb = sorted({tag.get(rf) for rf, _p in fnet.pins} & set(rigid), key=pos.get)
        if fb:
            feeds[fname] = {"angles": [fang], "boards": fb[:1],
                            "kind": "antenna_feed"}

    # ── Nose crown (2026-11-19): the crown is the TOP of the one-piece PEEK-LDS
    # sleeve, hanging on the Ø34 Al anchor ring. Each groove's LDS runs down the
    # sleeve's OUTER face to its own EDGE castellation on compute (allocated
    # below, after the core lanes, in a free rim slot — order-preserving so the
    # single-layer fan over the ring never crosses), soldered with the sides.
    crown = []
    if payloads:
        raw = {c.ref: getattr(c, "board_tag", None) for c in design.chips
               if getattr(c, "manf_pn", None) not in ("LGA_lands", MANF_PN)}
        cnets = set()
        users: dict = {}                      # crown net → payload boards using it
        for net in design.nets:
            if gnd is not None and (net is gnd or _is_gnd(net)):
                continue
            bs = {raw.get(rf) for rf, _p in net.pins} - {None}
            if bs & set(payloads) and bs - set(payloads):
                cnets.add(net.name)
                users[net.name] = sorted(bs & set(payloads))
        # allocated after the core lanes (below): needs compute's free rim slots

    # Guarded buses first: one contiguous run of angles (in ring order, so
    # the block is physically adjacent) free over the bus span.
    guarded = set()
    ring = sorted(angles, key=lambda a: (a - SIGNAL_SECTOR_CENTRE_DEG + 180.0) % 360.0)
    for _bus, (bus_nets, guard_key) in GUARDED_BUSES.items():
        nets_ = [design.net_by_name(n) for n in bus_nets]
        if any(n is None for n in nets_) or gnd is None:
            continue
        bset = set()
        for net in nets_:
            bset |= {tag.get(rf) for rf, _p in net.pins} & set(rigid)
        if len(bset) < 2:
            continue
        idx = sorted(pos[b] for b in bset)
        lo, hi = idx[0], idx[-1]
        span = [b for b in rigid if lo <= pos[b] <= hi]
        need = 2 * len(nets_) + 1
        # candidate runs nearest the sector centre first
        starts = sorted(range(len(ring) - need + 1),
                        key=lambda k: abs(((ring[k + need // 2] + 180.0) % 360.0) - 180.0))
        for k in starts:
            run = ring[k:k + need]
            step = math.degrees(CAST_PITCH_MM / r) * 1.5
            if any(abs(b - a) > step for a, b in zip(run, run[1:])):
                continue                   # not physically contiguous
            if all(free(a, lo, hi) for a in run):
                break
        else:
            print(f"  WARNING: castellations: no contiguous block for guarded "
                  f"bus {_bus}", file=sys.stderr)
            continue
        for a in run:
            occupied[a].append((lo, hi))
        for i, net in enumerate(nets_):
            lanes[net.name] = {"angles": [run[2 * i + 1]], "boards": span,
                               "kind": "signal", "width_mm": SIGNAL_LANE_WIDTH_MM,
                               "guarded_by": guard_key}
            guarded.add(net.name)
        lanes[guard_key] = {"angles": run[0::2], "boards": span, "net": gnd.name,
                            "kind": "gnd_guard", "width_mm": SIGNAL_LANE_WIDTH_MM}

    todo = []
    for net in design.nets:
        if net.name in guarded:
            continue
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
    # (2026-11-21) antenna-sector lanes may only START on a board above the
    # highest slot's UPPER board: a slot's copper patch reaches ~4 mm past its
    # gap, i.e. past the upper board's own castellation level (S1 in
    # wakeup↔power → patch up to ~2 mm above power) — so from compute up.
    _slot_up = [pos[s_.upper] for s_ in _ANT_SLOTS if s_.upper in pos]
    lo_upper = (max(_slot_up) + 1) if _slot_up else pos.get("wakeup_board", len(pos) + 1)
    # (2026-11-21) LOW antenna-sector lanes: a lane that stays BELOW a slot's
    # copper may use the antenna sector too (the battery-holder zone has no
    # antenna). For a lane topping out at board index hi, every slot whose
    # LOWER board is at or below hi has its patch reaching down to that
    # board's castellation level → the lane must stay out of that slot's
    # angular span (+ the patch margin). S4 sits in activation↔wakeup, so
    # aft → activation lanes may use 109-130° / 211-255°; S1 (wakeup↔power)
    # starts above activation and does not constrain them.
    from smash.parts.antenna_slots import PATCH_MARGIN_MM as _PM
    _pm_deg = math.degrees(_PM / 17.9) + 0.5 * math.degrees(CAST_PITCH_MM / r)

    def _low_angles(hi):
        if not upper_angles:
            return []
        spans = [s_.span_deg for s_ in _ANT_SLOTS if s_.lower in pos and pos[s_.lower] <= hi]
        return [a for a in upper_angles
                if all(not (sp[0] - _pm_deg <= a <= sp[1] + _pm_deg) for sp in spans)]
    # (2026-11-22) signal-sector-only lanes first, then the low lanes (which can
    # fall back to the antenna sector), each group longest-span first.
    # Low lanes with the FEWEST antenna-sector fallbacks go first, so the ones
    # that can still escape to the antenna sector yield the signal angles.
    def _order(t):
        low = t[1] < lo_upper - 1 and t[0] < lo_upper
        return (low, len(_low_angles(t[1])) if low else 0, -(t[1] - t[0]), t[0], t[2].name)
    todo.sort(key=_order)
    for lo, hi, net, bset in todo:
        need, got = _mult(net), []
        # antenna-sector-eligible lanes try those angles FIRST, keeping the
        # signal sector for the lanes that can only run there
        # (2026-11-22, user) LOW lanes (aft_end → activation) now try the
        # SIGNAL sector first: their battery-zone fan diagonals ran through
        # S4's ground patch from the antenna-sector angles. Antenna-sector low
        # angles stay as the fallback when the signal sector is full there.
        cand = (upper_angles + angles if lo >= lo_upper
                else angles + _low_angles(hi) if hi < lo_upper - 1 else angles)
        for a in cand:
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
    if nose_tile is not None:
        # (2026-11-21) fixed noses: every other payload board sits in the SAME
        # nose slot in its own config → it gets castellations at the nose
        # tile's lane angles for the nets it uses (+ the fixed GND ones).
        raw = {c.ref: getattr(c, "board_tag", None) for c in design.chips
               if getattr(c, "manf_pn", None) not in ("LGA_lands", MANF_PN)}
        others = [pb for pb in NI.PAYLOAD_BOARDS if pb in boards and pb != nose_tile]
        for name, ln in lanes.items():
            if nose_tile not in ln["boards"] or (gnd is not None and name == gnd.name):
                continue
            net = design.net_by_name(name)
            used = {raw.get(rf) for rf, _p in net.pins} if net is not None else set()
            ln["boards"] = list(ln["boards"]) + [pb for pb in others if pb in used]
        if gnd is not None and gnd.name in lanes:
            lanes[gnd.name]["boards"] = list(lanes[gnd.name]["boards"]) + others
    aft_cap = _aft_cap_contract(design, lanes, rigid, r, gnd, quiet=quiet)
    # Plug-ring exits on the aft board (rigid[0]).
    plug = []
    if plug_groups and rigid:
        taken = {a for ln in lanes.values() if rigid[0] in ln["boards"]
                 for a in ln["angles"]}
        taken |= {a for a in angles if not free(a, 0, 0)}
        taken |= {float(a) for a in ANTENNA_FEED_ANGLES_DEG.values()}
        slots = [a for a in _ring_angles(r)
                 if all(min(abs(a - t), 360 - abs(a - t)) > 0.5 * math.degrees(CAST_PITCH_MM / r)
                        for t in taken)]
        # Two half-shells (seam at 285°): whole groups go to half 1 until it
        # holds ~half the pads (or half 2 runs out of room), the rest to half 2.
        h1 = [a for a in slots if (a - SEAM_ANGLES_DEG[0]) % 360.0 < 180.0]
        h2 = [a for a in slots if (a - SEAM_ANGLES_DEG[0]) % 360.0 >= 180.0]
        total = sum(len(ns) for _l, ns in plug_groups)
        target1 = max(total - len(h2), (total + 1) // 2)
        src, k, n1 = h1, 0, 0
        for label, nets in plug_groups:
            if src is h1 and n1 + len(nets) > target1 and n1 >= total - len(h2):
                src, k = h2, 0
            for ref, net in nets:
                if k >= len(src):
                    print(f"  WARNING: castellations: plug ring short of exit "
                          f"slots at {ref}", file=sys.stderr)
                    break
                plug.append({"group": label, "ref": ref, "net": net,
                             "angle": src[k]})
                k += 1
                if src is h1:
                    n1 += 1
    # (2026-11-15) NOSE-CONE exits: the QPD / camera leaves sit in a custom
    # LDS nose cone that continues the sleeve above the parent. Each leaf net
    # (GND excluded — it rides the GND castellations) gets its own angle on
    # the parent, free from the parent to the top of the stack (where the
    # cone traces run), and a castellation at the same angle on the leaf PCB.
    # Allocated in the ANTENNA sector: above the parent, in the configs that
    # carry a cone (qpd / camera — never with radar), the sleeve
    # is empty there, and a cone trace over the sleeve's inner GND plane is a
    # microstrip. Clear of the GND castellations and the antenna feeds.
    half = 0.5 * math.degrees(CAST_PITCH_MM / r)
    fixed = list(GND_CAST_ANGLES_DEG) + list(ANTENNA_FEED_ANGLES_DEG.values())
    cone_slots = sorted(
        (a for a in _ring_angles(r) if not _in_signal_sector(a)
         and all(min(abs(a - f), 360 - abs(a - f)) > 2 * half for f in fixed)),
        key=lambda a: abs(a - 180.0))
    cone_used = set()
    cone_over = []
    # (2026-11-21) fixed noses: no cone exits — every payload net rides an
    # ordinary lane to the nose slot (see the parent map above)
    for parent, leaf, nets in ([] if (payloads or not NI.MODULAR) else (cone_exits or [])):
        if parent not in pos:
            continue
        for n in nets:
            net = design.net_by_name(n)
            if net is None or (gnd is not None and (net is gnd or _is_gnd(net))):
                continue
            a = next((a for a in cone_slots if a not in cone_used), None)
            if a is None:
                cone_over.append(n)
                continue
            cone_used.add(a)
            lanes[f"CONE:{leaf}:{n}"] = {"angles": [a], "boards": [parent, leaf],
                                         "net": net.name, "kind": "cone_exit",
                                         "width_mm": SIGNAL_LANE_WIDTH_MM}
        if gnd is not None and gnd.name in lanes and leaf in boards:
            lanes[gnd.name]["boards"] = list(dict.fromkeys(lanes[gnd.name]["boards"] + [leaf]))
    if cone_over:
        print(f"  WARNING: castellations: {len(cone_over)} nose-cone net(s) short "
              f"of angles: {', '.join(cone_over)}", file=sys.stderr)
    # Crown → compute castellations: free compute rim slots (whole ring — above
    # compute the antenna sector carries no antenna), clear of every other
    # compute castellation by one pitch and of the nose cone's retaining
    # plates (they cover the sleeve at the screw angles: no lane under / across
    # one → fans are assigned per sector between screws). Each sector gets at
    # most as many plated teeth as it has free slots; the rest stay unplated.
    crown_over, comp, crown_ring = [], {}, []
    if payloads:
        step = math.degrees(CAST_PITCH_MM / r)
        taken = [float(a) for ln in list(lanes.values()) + list(feeds.values())
                 if crown_host in ln.get("boards", []) and ln.get("kind") not in
                 ("crown_top", "crown_payload") for a in ln["angles"]]
        # (2026-11-20) snap hooks run INSIDE the bore: only the Ø1 release-pin
        # holes at the hook angles exclude lanes (was the 7 mm screw plate)
        plate_half = math.degrees((0.5 * NI.RELEASE_EXCL_W_MM + 0.4) / r)
        scr = sorted(NI.SCREW_ANGLES_DEG)
        free_slots = [a for a in _ring_angles(r)
                      # a FULL pitch from every other compute castellation: the
                      # GND / feed ones sit off the lane grid (124.5° vs 123°
                      # merged two vias into a slot)
                      if all(min(abs(a - t), 360 - abs(a - t)) >= step - 1e-6 for t in taken)
                      and all(min(abs(a - sa), 360 - abs(a - sa)) > plate_half for sa in scr)]
        caps = {}
        for a in free_slots:
            caps[NI.screw_sector(a)] = caps.get(NI.screw_sector(a), 0) + 1
        try:
            crown = NI.allocate(sorted(cnets), NI.group_order(cnets),
                                teeth=NI.usable_teeth(caps))
        except ValueError as e:
            crown_over = sorted(cnets)
            print(f"  WARNING: castellations: crown: {e} (free compute slots per "
                  f"sector {caps})", file=sys.stderr)
            crown = []
        # (2026-11-20) fan UNITS per sector: a run of adjacent teeth of one power
        # rail joins into ONE lane (Y over its teeth); GND teeth sit on the
        # crown's inner-edge LDS GND RING, which ONE GND lane per sector links
        # to compute. Units → slots by fan_slots (clearance along the diagonal).
        comp, units_of, ring = {}, {}, []
        pw = lambda role: POWER_LANE_WIDTH_MM if role in ("power", "gnd") else SIGNAL_LANE_WIDTH_MM
        for sk in range(len(scr)):
            start = scr[sk - 1]
            uw = lambda a: (a - start) % 360.0
            cs = sorted((c for c in crown if NI.screw_sector(c.angle_deg) == sk),
                        key=lambda c: uw(c.angle_deg))
            fs = [a for a in free_slots if NI.screw_sector(a) == sk]
            if not cs:
                continue
            gnds = [c for c in cs if c.role == "gnd"]
            ring += [c.tooth for c in gnds]
            # the ring link: the GND tooth nearest a free slot
            link = min(gnds, key=lambda c: min((abs(uw(c.angle_deg) - uw(a)) for a in fs),
                                               default=0.0)) if gnds else None
            units = []
            for c in cs:
                if c.role == "gnd" and c is not link:
                    continue
                u = units[-1] if units else None
                if (u and c.role == "power" and u["role"] == "power" and u["net"] == c.net
                        and c.tooth == u["teeth"][-1] + 1):
                    u["teeth"].append(c.tooth)
                    u["angles"].append(c.angle_deg)
                    continue
                units.append({"key": c.tooth, "teeth": [c.tooth], "angles": [c.angle_deg],
                              "net": c.net, "role": c.role})
            got, gap = NI.fan_slots([(u["key"], u["angles"], pw(u["role"])) for u in units],
                                    fs, start)
            if units and gap < NI.LANE_CLEAR_MM - 1e-6:
                print(f"  WARNING: castellations: crown fan sector {sk}: lane gap "
                      f"{gap:.2f} mm < {NI.LANE_CLEAR_MM} mm over the anchor band",
                      file=sys.stderr)
            for u in units:
                if u["key"] in got:
                    slot, lift = got[u["key"]]
                    u["lift"] = lift
                    units_of[u["key"]] = u
                    for k in u["teeth"]:
                        comp[k] = slot
        for c in crown:
            if c.tooth in ring and c.tooth not in comp:
                comp[c.tooth] = "ring"
        for c in crown:
            w = pw(c.role)
            used_by = users.get(c.net, list(payloads))
            if c.tooth not in comp:
                crown_over.append(c.net)
                continue
            # (2026-11-19) every crown lane is LASERED on every sleeve; a via is
            # only drilled where this payload uses the net (GND: always)
            u = units_of.get(c.tooth)
            if u is not None:
                lanes[f"CROWN:{c.tooth}:{c.net}"] = {
                    "angles": [comp[c.tooth]], "boards": [crown_host], "net": c.net,
                    "kind": "crown_top", "tooth": c.tooth, "tooth_angle": c.angle_deg,
                    "teeth": list(u["teeth"]), "tooth_angles": list(u["angles"]),
                    "fan_lift_mm": u.get("lift", 0.0),
                    "gnd_ring": c.role == "gnd", "width_mm": w, "payloads": used_by}
            lanes[f"CROWNP:{c.tooth}:{c.net}"] = {
                "angles": [c.angle_deg], "boards": list(payloads), "net": c.net,
                "kind": "crown_payload", "tooth": c.tooth, "width_mm": w,
                "payloads": used_by}
        crown_ring = sorted(ring)
        if crown_over:
            print(f"  WARNING: castellations: {len(crown_over)} crown contact(s) short of a "
                  f"compute rim slot", file=sys.stderr)
    debug = _debug_castellations(design, panel, boards, chain, pos, r, angles,
                                 upper_angles, occupied)
    # (2026-11-18) capacity counts the signal sector + the upper antenna-sector
    # angles (open to lanes from wakeup upward); a crown pad reservation only
    # occupies its angle at compute.
    used = sum(1 for a in angles + upper_angles if occupied[a])
    lanes.update(feeds)
    if overflow and not quiet:      # (lane_budget's "dedicated" estimate runs quiet)
        print(f"  WARNING: castellations: {len(overflow)} net(s) short of "
              f"lanes: {', '.join(overflow[:10])}", file=sys.stderr)
    return {"pitch_mm": CAST_PITCH_MM, "radius_mm": r,
            "lane_policy": policy, "overflow": list(overflow),
            "n_angles": len(angles) + len(upper_angles), "n_used": used,
            "reserved_deg": [list(s) for s in RESERVED_SECTORS_DEG],
            "signal_sector_deg": [SIGNAL_SECTOR_CENTRE_DEG - SIGNAL_SECTOR_HALF_DEG,
                                  SIGNAL_SECTOR_CENTRE_DEG + SIGNAL_SECTOR_HALF_DEG],
            "seam_deg": list(SEAM_ANGLES_DEG),
            "aft_board": rigid[0] if rigid else None,
            "crown": [dataclasses.asdict(c) for c in crown],
            "crown_host": crown_host, "crown_overflow": crown_over,
            "aft_cap": aft_cap,
            "crown_compute_angles": {c.tooth: comp[c.tooth] for c in crown if c.tooth in comp},
            "crown_gnd_ring": crown_ring,
            "plug": plug,
            "debug": debug,
            "lanes": lanes}


# DEBUG castellations: board-local debug nets on a castellation of their own
# board. No sleeve lane faces them (the tower leaves them open; a sleeve via
# at that angle brings one out later); on the dev board the escape stub ends
# on a test point. Allocated AFTER every lane, only at angles no lane uses at
# that board, so they never move a lane.
DEBUG_CASTELLATIONS = {
    "radar_module": ("AWR_TCK", "AWR_TMS", "AWR_TDI", "AWR_SOP0", "AWR_DBG_GPIO",
                     "AWR_1V2", "AWR_1V3", "AWR_1V8"),
    # wakeup_board, power_board: no edge room outside the S1/S4 keep-outs and the
    # lanes; their local nets are probed on component pads (BRING_UP.md).
    # camera_module has no castellations (flex-connected).
    "activation_interface": ("MAG_1V8", "TMR_VDD"),
}
# Bring-up test points for rails / control lines that already cross boards: the dev panel puts
# a test point at the end of that rail's castellation stub on the named board
# (no new castellation). Board-local rails are in DEBUG_CASTELLATIONS above.
RAIL_TEST_POINTS = {
    "COMP_3V3": "power_board", "COMP_1V8_AON": "power_board", "COMP_0V82": "power_board",
    "COMP_0V9": "power_board", "COMP_1V8": "power_board", "COMP_1V35": "power_board",
    "COMP_2V8": "power_board", "COMP_5V": "power_board", "COMP_5V_RAW": "power_board",
    "REG_IN_MAIN": "power_board", "ACTIVATE_HV": "power_board",
    # bring-up control / handshake lines that cross boards (BRING_UP.md):
    "COMP_OUT": "activation_interface", "IR_WAKE": "radar_module",
    "PWR_HOLD": "companion_compute", "PMIC_PWR_OK": "power_board",
    "ACTIVATE_BOOST_EN": "power_board", "MAIN_SW_GATE": "power_board",
    "RADAR_EN": "radar_module",
}
DEBUG_MIN_SEP_STEPS = 2      # debug pads ≥ 2 lane pitches apart (room for the dev test points)


def _debug_castellations(design, panel, boards, chain, pos, r, angles, upper_angles,
                         occupied) -> dict:
    """{board: [[angle, net], ...]}: each debug net on the free angle nearest
    its chip, antenna-sector angles first (they face away from the dev board's
    channel and keep the signal sector for lanes). Marks the angle occupied
    at that board only."""
    out: dict = {}
    if not DEBUG_CASTELLATIONS:
        return out
    M = board_fold_transforms(panel, chain)
    step = math.degrees(CAST_PITCH_MM / r)

    def adist(a, b):
        return abs(((a - b + 180.0) % 360.0) - 180.0)
    from smash.parts.antenna_slots import KEEPOUT_HALFWIDTH_MM, BOARD_R_MM
    _ko = math.degrees(KEEPOUT_HALFWIDTH_MM / BOARD_R_MM) + 0.5 * step
    for b, nets in DEBUG_CASTELLATIONS.items():
        if b not in pos or b not in M or b not in boards:
            continue
        k = pos[b]
        # a board next to a slot keeps that slot's antenna keep-out wedge
        # (span ± keep-out half-width) free of debug copper
        ko = [(s_.span_deg[0] - _ko, s_.span_deg[1] + _ko) for s_ in _ANT_SLOTS
              if b in (s_.lower, s_.upper)]

        def free_at(a):
            return (all(not (lo <= k <= hi) for lo, hi in occupied[a])
                    and all(not (a0 <= a <= a1) for a0, a1 in ko))
        place = {pl.item.ref: pl.position_mm for pl in boards[b].chip_placements
                 if getattr(pl.item, "board_tag", b) == b}
        taken: list = []
        for net_name in nets:
            net = design.net_by_name(net_name)
            if net is None:
                continue
            refs = [p[0] for p in net.pins if p[0] in place]
            refs.sort(key=lambda ref: (not ref.startswith("U_"), ref))
            xy = place[refs[0]] if refs else (0.0, 0.0)
            best = None
            for group in (upper_angles, angles):
                cands = [a for a in group if free_at(a)
                         and all(adist(a, t) >= DEBUG_MIN_SEP_STEPS * step - 1e-6 for t in taken)]
                if cands:
                    best = min(cands, key=lambda a: (math.dist(_local_xy(M[b], a, r), xy), a))
                    break
            if best is None:
                print(f"  WARNING: castellations: no free angle for debug net {net_name} "
                      f"on {b}", file=sys.stderr)
                continue
            occupied[best].append((k, k))
            taken.append(best)
            out.setdefault(b, []).append([round(best, 4), net_name])
    return out


AFT_CAP_TAG = "aft_end_cap"         # virtual board of the aft public-interface contacts
# (2026-11-19) the cap crown has its OWN, finer grid (independent of the nose
# crown): 60 positions at 6°, phase 3° — room for the battery-zone fan.
AFT_CAP_N_TEETH = 60
AFT_CAP_PHASE_DEG = 3.0
AFT_CAP_SCREW_TEETH = (4, 25, 45)   # 27 / 153 / 273° — between the cells; uneven = the key
# (2026-11-23, user) the stacking fixture's rim pin passes the cap: the tooth at
# the pin angle (285°) carries no contact (a Ø1.2 hole at r 16.5 instead)
AFT_CAP_PIN_TEETH: tuple = ()     # (2026-11-23, user) the sleeve's rib keys the stack: no pin through the cap


def aft_tooth_angle(k: int) -> float:
    return round((AFT_CAP_PHASE_DEG + k * 360.0 / AFT_CAP_N_TEETH) % 360.0, 4)


def _aft_cap_contract(design, lanes: dict, rigid: list, r: float, gnd,
                      quiet: bool = False) -> dict | None:
    """(2026-11-19, user) aft_end_cap crown: every net with a contact on the cap
    (board_tag AFT_CAP_TAG) keeps its sleeve lane, which now runs down past the
    aft board to the aft rim (no castellation on the aft board unless the net
    really has a pin there) and fans over the cap's outer skin into its groove.
    Teeth are assigned ORDER-PRESERVING to the lanes' angles (no crossings);
    three blank SCREW positions (uneven = the key); spare teeth are GND, joined by an
    LDS ring at the crown's inner edge and linked to the nearest GND
    castellation on the aft board."""
    from smash.export import nose_interface as NI
    if not rigid:
        return None
    aft = rigid[0]
    cap_refs = {c.ref for c in design.chips if getattr(c, "board_tag", None) == AFT_CAP_TAG}
    if not cap_refs:
        return None
    on_aft = {c.ref for c in design.chips if getattr(c, "board_tag", None) == aft}
    cap_nets, label = [], {}
    for net in design.nets:
        refs = {rf for rf, _p in net.pins}
        if not refs & cap_refs or (gnd is not None and (net is gnd or _is_gnd(net))):
            continue
        cap_nets.append(net.name)
        label[net.name] = sorted(rf.removeprefix("TP_") for rf in refs & cap_refs)[0]
        ln = lanes.get(net.name)
        if ln is None:
            continue
        ln["aft_cap"] = True
        if not refs & on_aft and aft in ln.get("boards", []):
            ln["boards"] = [b for b in ln["boards"] if b != aft]     # no aft castellation
    missing = [n for n in cap_nets if n not in lanes or not lanes[n]["angles"]]
    # (2026-11-19, user) The FAN happens on the sleeve alongside the BATTERY
    # compartment (no antennas, ~24 mm tall), not on the cap skin. Every lane
    # crossing that zone takes part, in ONE cyclic order (so none cross):
    #   • cap lanes  → a crown TOOTH angle (then straight down onto the cap);
    #   • aft-board lanes (their own castellations on the aft board) → a
    #     castellation slot BETWEEN teeth (tooth + half a pitch); the aft
    #     board's castellation moves there.
    # Three SCREW positions (no groove, no label; uneven = the key).
    pitch = 360.0 / AFT_CAP_N_TEETH
    start = aft_tooth_angle(AFT_CAP_SCREW_TEETH[0])
    unwrap = lambda a: (a - start) % 360.0
    teeth = [k for k in range(AFT_CAP_N_TEETH)
             if k not in AFT_CAP_SCREW_TEETH and k not in AFT_CAP_PIN_TEETH]
    fixed = [float(a) for a in GND_CAST_ANGLES_DEG] + [float(a) for a in ANTENNA_FEED_ANGLES_DEG.values()]
    step = math.degrees(CAST_PITCH_MM / r)
    # Bottom positions on a FINE grid (0.25°): cap lanes exactly on a usable
    # tooth; aft-board lanes anywhere ≥ one lane pitch from the fixed GND /
    # feed castellations; consecutive bottoms ≥ one lane pitch apart.
    RES = 0.25
    NPOS = int(round(360.0 / RES))
    tooth_set = {round(unwrap(aft_tooth_angle(k)) / RES) for k in teeth}
    def dfix(a):
        return min((min(abs(a - f) % 360.0, 360.0 - abs(a - f) % 360.0) for f in fixed),
                   default=999.0)
    m_ok = [dfix((start + q * RES) % 360.0) >= step for q in range(NPOS)]
    items = []                                     # (unwrapped lane angle, type, lane key)
    for n in cap_nets:
        if n in lanes and lanes[n]["angles"]:
            items.append((unwrap(lanes[n]["angles"][0]), "T", n))
    for key, ln in lanes.items():
        if (ln.get("aft_cap") or ln.get("kind") in ("gnd_plane", "antenna_feed",
                                                    "crown_top", "crown_payload")):
            continue
        if aft in ln.get("boards", []) and ln["angles"]:
            items.append((unwrap(ln["angles"][0]), "M", key))
    items.sort()
    SEP = int(math.ceil(step / RES))
    # (2026-11-20) single-layer LDS: two WIDE (power) neighbours running a
    # long parallel jog close up to (spacing × cos φ). So: wide pairs start
    # further apart, and a wide lane's jog is limited to tan φ ≤ JOG_TAN over
    # the zone (≈ cell length) — keeps ≥ the LDS clearance along the diagonal.
    from smash.layout.boards.smash_evb_v1 import BATTERY_LENGTH_MM
    R_SKIN, CLR, JOG_TAN = 17.9, 0.20, 0.45      # CLR: LDS spacing (LPKF DR_013, recommended)
    jog_max = math.degrees(JOG_TAN * (BATTERY_LENGTH_MM - 2.0) / R_SKIN)
    wid = lambda it: lanes[it[2]].get("width_mm", 0.2)
    def sep_q(a, b):
        need = 0.5 * (wid(a) + wid(b)) + CLR + 0.1
        return max(SEP, int(math.ceil(math.degrees(need / R_SKIN) / RES)))
    INF = float("inf")
    I = len(items)

    def _solve(t_tan):
        """Order-preserving DP; wide M lanes jog ≤ JOG_TAN, wide T (cap-tooth)
        lanes ≤ t_tan (None = free) over the zone height."""
        t_max = (math.degrees(t_tan * (BATTERY_LENGTH_MM - 2.0) / R_SKIN)
                 if t_tan is not None else None)

        def ok(it, q):
            if it[1] == "T":
                # a cap lane that ALSO lands on the aft board (crown ESD there)
                # gets an aft castellation at its tooth: keep it ≥ one lane pitch
                # off the fixed GND / feed castellations, like the aft-only lanes
                good = q in tooth_set and (m_ok[q] or aft not in lanes[it[2]].get("boards", []))
            else:
                good = m_ok[q]
            if good and wid(it) > 0.4:
                lim = jog_max if it[1] == "M" else t_max
                if lim is not None:
                    d = abs(q * RES - it[0]) % 360.0
                    good = min(d, 360.0 - d) <= lim
            return good
        cost = [[INF] * NPOS for _ in range(I)]
        back = [[-1] * NPOS for _ in range(I)]
        for q in range(NPOS if items else 0):
            if ok(items[0], q):
                cost[0][q] = abs(q * RES - items[0][0])
        for i in range(1, I):
            best, arg = INF, -1
            sep_i = sep_q(items[i - 1], items[i])
            for q in range(NPOS):
                qq = q - sep_i
                if qq >= 0 and cost[i - 1][qq] < best:
                    best, arg = cost[i - 1][qq], qq
                if best < INF and ok(items[i], q):
                    cost[i][q] = best + abs(q * RES - items[i][0])
                    back[i][q] = arg
        if not items or min(cost[I - 1]) == INF:
            return None
        out = {}
        q = min(range(NPOS), key=lambda x: cost[I - 1][x])
        for i in range(I - 1, -1, -1):
            out[items[i][2]] = round((start + q * RES) % 360.0, 4)
            q = back[i][q]
        return out
    # (2026-11-20) wide cap-tooth lanes too: two 0.6 mm lanes jogging ~60° side
    # by side closed to 0.03 mm. Tightest jog cap that still fits wins.
    assign = {}
    for t_tan in (JOG_TAN, 0.6, 0.8, None):
        got = _solve(t_tan)
        if got is not None:
            assign = got
            break
    by_angle = {round(aft_tooth_angle(k), 4): k for k in teeth}
    used = {}
    n_fan = 0
    missing += [key for _u, typ, key in items if typ == "T" and key not in assign]
    for _u, typ, key in items:
        b = assign.get(key)
        if b is None:
            continue
        ln = lanes[key]
        ln["fan"] = {"top_deg": ln["angles"][0], "bottom_deg": b}
        n_fan += 1
        if typ == "M" or aft in ln.get("boards", []):
            ln.setdefault("board_angles", {})[aft] = [b]     # aft castellation moves
        if typ == "T":
            b = aft_tooth_angle(by_angle[round(b, 4)])
            ln["fan"]["bottom_deg"] = b
            used[by_angle[round(b, 4)]] = {"tooth": by_angle[round(b, 4)], "angle_deg": b, "net": key,
                                 "lane_angle": ln["angles"][0], "role": "signal",
                                 "label": label.get(key, key)}
    out = []
    for k in range(AFT_CAP_N_TEETH):
        if k in AFT_CAP_SCREW_TEETH:
            out.append({"tooth": k, "angle_deg": aft_tooth_angle(k), "net": None,
                        "role": "screw", "label": ""})
        elif k in AFT_CAP_PIN_TEETH:                       # alignment-pin hole, no contact
            out.append({"tooth": k, "angle_deg": aft_tooth_angle(k), "net": None,
                        "role": "key", "label": ""})
        elif k in used:
            out.append(used[k])
        else:
            out.append({"tooth": k, "angle_deg": aft_tooth_angle(k),
                        "net": gnd.name if gnd is not None else "GND", "role": "gnd",
                        "label": "GND"})
    # GND link: the GND tooth nearest a GND castellation on the aft board
    g_angles = list(GND_CAST_ANGLES_DEG)
    best = None
    for t in out:
        if t["role"] != "gnd":
            continue
        for ga in g_angles:
            d = min(abs(t["angle_deg"] - ga), 360 - abs(t["angle_deg"] - ga))
            if best is None or d < best[0]:
                best = (d, t["tooth"], ga)
    if missing and not quiet:
        print(f"  WARNING: aft_end_cap: {len(missing)} net(s) without a cap tooth / lane: "
              f"{', '.join(missing[:8])}", file=sys.stderr)
    return {"n_teeth": AFT_CAP_N_TEETH, "screw_teeth": list(AFT_CAP_SCREW_TEETH), "contacts": out,
            "fan_zone": [aft, rigid[1] if len(rigid) > 1 else aft], "n_fan": n_fan,
            "gnd_link": ({"tooth": best[1], "castellation_deg": best[2]} if best else None),
            "missing": missing}


def lane_budget(design, panel, boards, cone_exits=None) -> dict:
    """Signal-sector angle budget under both lane policies:
    {policy: {"n_angles", "n_used", "overflow": [net names]}}. With "dedicated"
    an overflow lists the nets that do NOT fit — nothing falls back silently."""
    out = {}
    for pol in ("reuse", "dedicated"):
        c = castellation_contract(design, panel, boards, cone_exits=cone_exits,
                                  lane_policy=pol, quiet=True)
        out[pol] = {"n_angles": c["n_angles"], "n_used": c["n_used"],
                    "overflow": c["overflow"]}
    return out


def place_castellations(design, panel, boards, *, connect,
                        contract: dict | None = None, plug_groups=None,
                        cone_exits=None) -> tuple:
    """Emit one CASTELLATIONS chip per rigid snake board (pads on the outline
    at the contract's lanes, mapped into the board's folded frame). Computes
    the contract when none is given. Returns (contract, {board: n_pads})."""
    from smash.state.topology.placement import Placement
    if contract is None:
        contract = castellation_contract(design, panel, boards, plug_groups,
                                         cone_exits=cone_exits)
    chain = [n for n in (panel.snake_chain or []) if n in boards]
    M = board_fold_transforms(panel, chain)
    # Branch leaves (nose-cone PCBs) take their parent's frame, own radius.
    for src, dst in (getattr(panel, "branches", None) or []):
        if src in M and dst in boards:
            M.setdefault(dst, M[src])
    r = contract["radius_mm"]

    def r_of(b):
        g = getattr(boards[b], "geometry", None)
        return getattr(g, "outline_radius_mm", None) or r
    per_board: dict = {}
    for net_name, lane in contract["lanes"].items():
        for b in lane["boards"]:
            if b in boards and b in M:
                # (2026-11-19) a lane may meet one board at another angle (the
                # battery-zone fan moves the aft board's castellations)
                for a in lane.get("board_angles", {}).get(b, lane["angles"]):
                    per_board.setdefault(b, []).append((a, net_name))
    for b, items in (contract.get("debug") or {}).items():
        if b in boards and b in M:
            for a, net_name in items:
                per_board.setdefault(b, []).append((a, net_name))
    ab = contract.get("aft_board")
    for e in contract.get("plug", []):
        if ab in boards and ab in M:
            per_board.setdefault(ab, []).append((e["angle"], e["net"]))
    counts = {}
    dbg_nets = {b: {n for _a, n in its} for b, its in (contract.get("debug") or {}).items()}
    for b, items in per_board.items():
        # lanes numbered in angle order; debug pads AFTER them (adding one
        # never renumbers a lane pad)
        items.sort(key=lambda it: (it[1] in dbg_nets.get(b, ()), it[0]))
        pads = []
        for i, (a, _n) in enumerate(items):
            pads.append(Pad(num=str(i + 1), position_mm=_local_xy(M[b], a, r_of(b)),
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
                       pads=pads, size_mm=(2 * r_of(b), 2 * r_of(b)), height_mm=0.0,
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
        for k, (_a, key) in enumerate(items):
            net_name = contract["lanes"].get(key, {}).get("net", key)
            if design.net_by_name(net_name) is not None or any(
                    net_name in (n.aliases or []) for n in design.nets):
                connect(net_name, chip.pin(str(k + 1)))
        boards[b].chip_placements.append(Placement(
            position_mm=(0.0, 0.0), rotation_deg=0.0, item=chip,
            face="top", locked=True))
        counts[b] = len(pads)
    return contract, counts

