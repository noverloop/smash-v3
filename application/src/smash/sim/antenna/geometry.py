"""Parametric, solver-free model of the potted tower + LDS sleeve + printed
HF slot antennas, as annular-sector prisms ("sectors").

Pure Python (no openEMS import) so it is unit-testable; the runner turns
the sectors into CSXCAD primitives (`AddCylinder` / `AddRotPoly`).

Frame: z up from the bottom face of aft_end_board, angles in the sleeve's
PHYSICAL frame (castellations.py: antenna sector 105°…255°, GND
castellations 113/120/240/247°). ⚠ The cell triangle is taken in the same
frame as the board-local battery bore (`_battery_bore_polygon`: centres at
90° + k·120° by default) — confirm that the board frame and the sleeve
frame coincide before reading angles off the cell gaps.

Board levels: measured on the generated sleeve unroll (dist/stackup.kicad_pcb,
2026-11-16) — mid-planes relative to aft_end, fitted board thickness
1.315 mm. Every rigid board is modelled as a PEC disc (8 copper layers ≈ a
solid ground at these wavelengths) with optional copper keep-out wedges.
"""
from __future__ import annotations

import dataclasses
import math

from smash.export.sleeve_step import SLEEVE_GAP_MM, SLEEVE_WALL_MM
from smash.export.spacer_step import RING_R_IN_MM, RING_R_OUT_MM
from smash.parts.castellations import GND_CAST_ANGLES_DEG

BOARD_R_MM = 17.0
BOARD_T_MM = 1.315
SLEEVE_R_IN_MM = BOARD_R_MM + SLEEVE_GAP_MM
SLEEVE_R_OUT_MM = SLEEVE_R_IN_MM + SLEEVE_WALL_MM
ANTENNA_SECTOR_DEG = (105.0, 255.0)

# Board mid-planes [mm above aft_end's bottom face] from the sleeve unroll.
BOARD_MID_Z_MM = {
    "aft_end_board": 0.66,
    "activation_interface": 26.17,
    "fin_ble_board": 31.89,
    "wakeup_board": 36.20,
    "power_board": 41.92,
    "companion_compute": 46.43,
    "radar_module": 51.85,
}
CORE_BOARDS = ("aft_end_board", "activation_interface", "fin_ble_board",
               "wakeup_board", "power_board", "companion_compute")
RADAR_BOARDS = CORE_BOARDS + ("radar_module",)
# (2026-11-18) The nose_cap PCB is retired: the stack is closed by the cup's
# PEEK-LDS end wall (one moulding with the sleeve), CUP_END_GAP_MM above the
# top board, CUP_END_T_MM thick — modelled in sleeve material, potting below.
CUP_END_GAP_MM = 2.0
CUP_END_T_MM = 1.0

# Battery compartment (3 × TLM-1520HPM/S standing, 21 mm cells).
CELL_R_MM = 7.25
CELL_CLUSTER_R_MM = 8.6
CELL_Z_MM = (2.5, 23.5)
HOLDER_R_IN_MM = 16.2           # 0.8 mm skin to the Ø34 envelope


@dataclasses.dataclass(frozen=True)
class Sector:
    """Annular-sector prism: r_in ≤ r ≤ r_out, a0 ≤ θ ≤ a1 (deg), z0 ≤ z ≤ z1.
    r_in = 0 and a full turn → a plain cylinder. Higher priority wins."""
    name: str
    material: str          # "pec" or a materials.ALL key
    r_in: float
    r_out: float
    z0: float
    z1: float
    a0: float = 0.0
    a1: float = 360.0
    priority: int = 10

    @property
    def full_turn(self) -> bool:
        return (self.a1 - self.a0) >= 360.0 - 1e-9


@dataclasses.dataclass(frozen=True)
class Port:
    """50 Ω lumped feed bridging a slot. `axis`: "tangential" (axial slot —
    the gap is across θ) or "z" (arc slot — the gap is across z)."""
    name: str
    angle_deg: float
    r: float
    z: float
    axis: str
    gap_mm: float


@dataclasses.dataclass(frozen=True)
class Slot:
    """One printed slot in the outer-face copper skin.
    kind "axial": runs along z from `z_start` by `length` (sign = direction),
    centred on `angle_deg`. kind "arc": runs round the sleeve from
    `angle_deg` by `length` (sign = direction) at height `z_start`.
    kind "L": axial for `length`, then an arc of `arc_length` from its far
    end. The feed sits `feed_offset` along the slot from its START end."""
    name: str
    kind: str
    angle_deg: float
    z_start: float
    length: float
    width: float = 1.5
    feed_offset: float = 4.0
    arc_length: float = 0.0
    f_design_ghz: float = 0.0

    def sectors(self, r_in: float, r_out: float, material: str, prio: int) -> list:
        out = []
        dth = math.degrees(self.width / r_out)
        if self.kind in ("axial", "L"):
            z0, z1 = sorted((self.z_start, self.z_start + self.length))
            out.append(Sector(f"{self.name}_ax", material, r_in, r_out, z0, z1,
                              self.angle_deg - dth / 2, self.angle_deg + dth / 2, prio))
        if self.kind == "arc":
            a = math.degrees(self.length / r_out)
            a0, a1 = sorted((self.angle_deg, self.angle_deg + a))
            out.append(Sector(f"{self.name}_arc", material, r_in, r_out,
                              self.z_start - self.width / 2, self.z_start + self.width / 2,
                              a0, a1, prio))
        if self.kind == "L" and self.arc_length:
            z_end = self.z_start + self.length
            a = math.degrees(self.arc_length / r_out)
            a0, a1 = sorted((self.angle_deg, self.angle_deg + a))
            zc = z_end - math.copysign(self.width / 2, self.length)
            out.append(Sector(f"{self.name}_arc", material, r_in, r_out,
                              zc - self.width / 2, zc + self.width / 2, a0, a1, prio))
        return out

    def port(self, r: float) -> Port:
        if self.kind == "arc":
            ang = self.angle_deg + math.copysign(math.degrees(self.feed_offset / r), self.length)
            return Port(f"P_{self.name}", ang, r, self.z_start, "z", self.width)
        z = self.z_start + math.copysign(self.feed_offset, self.length)
        return Port(f"P_{self.name}", self.angle_deg, r, z, "tangential", self.width)

    @property
    def total_length(self) -> float:
        return abs(self.length) + abs(self.arc_length)


@dataclasses.dataclass
class TowerModel:
    sectors: list
    ports: list
    slots: list
    z_extent: tuple
    notes: list


def half_wave_slot_mm(f_ghz: float, eps_eff: float) -> float:
    """Resonant half-wave slot length λ_eff/2 [mm]."""
    return 299.792458 / f_ghz / 2.0 / math.sqrt(eps_eff)


def cell_gap_angles(cell_rot_deg: float = 90.0) -> list:
    """Angles [deg] midway between the three cells (the deep spots)."""
    return sorted(((cell_rot_deg + 60.0 + 120.0 * k) % 360.0) for k in range(3))


def build_tower(*, boards=CORE_BOARDS, slots=(), potting="potting_black",
                holder="al", cell_rot_deg: float = 90.0, rings="al",
                ring_free_sector=None, ring_setback_mm: float = 0.0,
                ring_setback_gaps: tuple | None = None,
                ring_open_margin_mm: float | None = None,
                ring_wall_mm: float | None = None,
                sleeve_mat: str = "lds_lcp",
                ring_al_gaps: tuple | None = None,
                ring_insert: str = "peek", keepout_depth_mm: float = 0.0,
                keepout_halfwidth_mm: float = 4.0,
                keepout_slots: tuple | None = None, sleeve_inner_gnd: bool = False,
                skin: str = "sector", skin_margin_mm: float = 4.0,
                skin_clip_deg: tuple | None = None,
                coating_mm: float = 0.0, housing=None, feed: str = "ideal",
                feed_board: str = "wakeup_board", cpw_w_mm: float = 1.0,
                cpw_gap_mm: float = 0.5, cpw_gnd_mm: float = 2.0) -> TowerModel:
    """Assemble the tower.

    holder: "al" (PEC skin) | "composite".   rings: "al" | "peek" | "none".
    ring_free_sector: (a0, a1) where Al rings are cut away (rings="al" only).
    ring_setback_mm > 0: instead of the cut, the Al wall steps inward by that
    much over ring_free_sector and `ring_insert` (PEEK) fills the space in
    front of it up to the sleeve — a slot cavity with no potting in it.
    keepout_*: copper-free wedge cut into every board under each slot
    (radial depth from the edge, ± half-width around the slot line).
    skin: "sector" — copper over the whole antenna sector (forms a closed
    parallel-plate cavity with the tower metal 0.4–1 mm below); "local" — a
    narrow copper patch per slot, `skin_margin_mm` beyond the slot on every
    side (2026-11-16, after the sector skin trapped the energy).
    housing: None (uncovered sleeve, option D) or dict(window=(z0, z1, a0, a1))
    for a metal tube Ø(sleeve OD + coating)… with an open window.
    feed: "ideal" — a lumped port straight across the slot at its feed point;
    "castellation" (2026-11-17, arc slots only) — the real path: the radio
    board's castellation at the slot's feed angle (z = `feed_board` mid-plane)
    → a coplanar line on the sleeve's outer face (strip `cpw_w_mm`, gaps
    `cpw_gap_mm`, ground bands `cpw_gnd_mm` joined to the slot's copper patch)
    → the strip crosses the slot and lands on the far-side copper. The port
    sits at the board end, across one CPW gap, so Zin includes the line.
    """
    S, notes = [], []
    zb = [BOARD_MID_Z_MM[b] for b in boards]
    z_lo = BOARD_MID_Z_MM[boards[0]] - BOARD_T_MM / 2
    z_hi = BOARD_MID_Z_MM[boards[-1]] + BOARD_T_MM / 2
    # potting fills the sleeve bore; the sleeve wall around it.
    S.append(Sector("potting", potting, 0.0, SLEEVE_R_IN_MM, z_lo, z_hi, priority=1))
    S.append(Sector("sleeve_wall", sleeve_mat, SLEEVE_R_IN_MM, SLEEVE_R_OUT_MM, z_lo, z_hi, priority=2))
    # cup: potting continues past the top board up to the closed end wall
    # (same moulding / material as the sleeve).
    z_end = z_hi + CUP_END_GAP_MM
    S.append(Sector("cup_potting", potting, 0.0, SLEEVE_R_IN_MM, z_hi, z_end, priority=1))
    S.append(Sector("cup_wall", sleeve_mat, SLEEVE_R_IN_MM, SLEEVE_R_OUT_MM, z_hi, z_end, priority=2))
    S.append(Sector("cup_end", sleeve_mat, 0.0, SLEEVE_R_OUT_MM, z_end, z_end + CUP_END_T_MM,
                    priority=2))
    # boards: FR-4 is irrelevant under a PEC disc model — ground disc per board.
    for b in boards:
        zm = BOARD_MID_Z_MM[b]
        S.append(Sector(f"board_{b}", "pec", 0.0, BOARD_R_MM, zm - BOARD_T_MM / 2,
                        zm + BOARD_T_MM / 2, priority=5))
    # keep-out wedges on every board a slot passes over.
    if keepout_depth_mm > 0:
        for sl in slots:
            if keepout_slots is not None and sl.name not in keepout_slots:
                continue        # copper board edge stays (closes that slot's gap)
            for sec in sl.sectors(0, SLEEVE_R_OUT_MM, "x", 0):
                for b in boards:
                    zm = BOARD_MID_Z_MM[b]
                    if sec.z1 < zm - BOARD_T_MM / 2 - 1.0 or sec.z0 > zm + BOARD_T_MM / 2 + 1.0:
                        continue
                    hw = math.degrees(keepout_halfwidth_mm / BOARD_R_MM)
                    a0, a1 = sec.a0 - hw, sec.a1 + hw
                    S.append(Sector(f"keepout_{sl.name}_{b}", "fr4",
                                    BOARD_R_MM - keepout_depth_mm, BOARD_R_MM,
                                    zm - BOARD_T_MM / 2, zm + BOARD_T_MM / 2, a0, a1, priority=6))
    # gap rings (every non-battery gap).
    if rings != "none":
        for lo, hi in zip(boards[1:-1], boards[2:]):
            z0 = BOARD_MID_Z_MM[lo] + BOARD_T_MM / 2
            z1 = BOARD_MID_Z_MM[hi] - BOARD_T_MM / 2
            mat = "pec" if rings == "al" else "peek"
            r_ring_in = RING_R_OUT_MM - ring_wall_mm if ring_wall_mm else RING_R_IN_MM
            if ring_al_gaps and lo in ring_al_gaps:      # (2026-11-17) per-gap: 1 mm Al
                mat, r_ring_in = "pec", RING_R_OUT_MM - 1.0
            S.append(Sector(f"ring_{lo}", mat, r_ring_in, RING_R_OUT_MM, z0, z1, priority=4))
            free = ring_free_sector
            if ring_open_margin_mm is not None:
                # (2026-11-17) structural rings: open ONLY behind a slot in
                # this gap, over its span ± margin; other gaps: full ring.
                dm = math.degrees(ring_open_margin_mm / (0.5 * (RING_R_IN_MM + RING_R_OUT_MM)))
                spans = [sec for sl in slots for sec in sl.sectors(0, SLEEVE_R_OUT_MM, "x", 0)
                         if z0 <= 0.5 * (sec.z0 + sec.z1) <= z1]
                free = ((min(sp.a0 for sp in spans) - dm, max(sp.a1 for sp in spans) + dm)
                        if spans else None)
            if rings == "al" and free:
                a0, a1 = free
                # ring_setback_gaps: lower boards of the gaps that get the step
                # (None = every gap). 2026-11-17: the step kills S1 at 2.15 GHz
                # but lifts S4 (4-7 GHz) to 57-88 % — so per gap.
                if ring_setback_mm > 0 and (ring_setback_gaps is None
                                            or lo in ring_setback_gaps):
                    # STEPPED ring (2026-11-17): over the free sector the Al wall
                    # steps inward (radial end walls at the sector edges) and a
                    # low-loss insert fills the space in front of it up to the
                    # sleeve — the slot's cavity is boards + stepped wall +
                    # insert, with no potting in it.
                    w = RING_R_OUT_MM - RING_R_IN_MM
                    rb = RING_R_OUT_MM - ring_setback_mm
                    S.append(Sector(f"ring_insert_{lo}", ring_insert, rb, SLEEVE_R_IN_MM,
                                    z0, z1, a0, a1, priority=7))
                    S.append(Sector(f"ring_step_{lo}", "pec", rb - w, rb, z0, z1, a0, a1, priority=7))
                    da = math.degrees(w / (0.5 * (rb - w + RING_R_IN_MM)))
                    S.append(Sector(f"ring_end_a_{lo}", "pec", rb - w, RING_R_IN_MM,
                                    z0, z1, a0 - da, a0, priority=7))
                    S.append(Sector(f"ring_end_b_{lo}", "pec", rb - w, RING_R_IN_MM,
                                    z0, z1, a1, a1 + da, priority=7))
                else:
                    S.append(Sector(f"ring_cut_{lo}", potting, RING_R_IN_MM, RING_R_OUT_MM,
                                    z0, z1, a0, a1, priority=7))
    # battery compartment: holder skin + floor, three cells.
    if "aft_end_board" in boards and "activation_interface" in boards:
        hz0 = BOARD_MID_Z_MM["aft_end_board"] + BOARD_T_MM / 2
        hz1 = BOARD_MID_Z_MM["activation_interface"] - BOARD_T_MM / 2
        hmat = "pec" if holder == "al" else "composite"
        S.append(Sector("holder_skin", hmat, HOLDER_R_IN_MM, BOARD_R_MM, hz0, hz1, priority=4))
        S.append(Sector("holder_floor", hmat, 0.0, BOARD_R_MM, hz0, hz0 + 1.2, priority=4))
        # The compartment is NOT potted (user, 2026-11-16): the real holder is
        # a solid block with three cell bores (spacer_step BATT_*), so holder
        # material up to the cell tops, air in the headroom above them. Cells
        # (priority 4) still win over the block.
        S.append(Sector("holder_block", hmat, 0.0, HOLDER_R_IN_MM, hz0, CELL_Z_MM[1], priority=3))
        S.append(Sector("holder_headroom", "air", 0.0, HOLDER_R_IN_MM, CELL_Z_MM[1], hz1, priority=3))
        for k in range(3):
            a = math.radians(cell_rot_deg + 120.0 * k)
            S.append(_offset_cylinder(f"cell{k + 1}", CELL_CLUSTER_R_MM * math.cos(a),
                                      CELL_CLUSTER_R_MM * math.sin(a), CELL_R_MM,
                                      *CELL_Z_MM))
        notes.append(f"cells at {[round((cell_rot_deg + 120 * k) % 360, 1) for k in range(3)]}°, "
                     f"gaps at {cell_gap_angles(cell_rot_deg)}° — holder {holder}")
    # inner-face sleeve GND plane (the old placeholder ground) — off by default.
    if sleeve_inner_gnd:
        S.append(Sector("sleeve_inner_gnd", "pec", SLEEVE_R_IN_MM, SLEEVE_R_IN_MM + 0.4,
                        z_lo, z_hi, *ANTENNA_SECTOR_DEG, priority=8))
    # outer copper skin over the antenna sector, slots cut through it.
    skin_z = (min(zb) - BOARD_T_MM / 2, max(zb) + BOARD_T_MM / 2)
    skin_r_in = SLEEVE_R_OUT_MM - 0.4          # ≥ 1 FDTD cell so the sheet survives meshing
    if skin == "sector":
        S.append(Sector("skin", "pec", skin_r_in, SLEEVE_R_OUT_MM, *skin_z,
                        *ANTENNA_SECTOR_DEG, priority=9))
    elif skin == "local":
        dm = math.degrees(skin_margin_mm / SLEEVE_R_OUT_MM)
        for sl in slots:
            for sec in sl.sectors(skin_r_in, SLEEVE_R_OUT_MM, "pec", 9):
                S.append(dataclasses.replace(
                    sec, name=f"skin_{sec.name}",
                    z0=max(sec.z0 - skin_margin_mm, skin_z[0]),
                    z1=min(sec.z1 + skin_margin_mm, skin_z[1]),
                    a0=max(sec.a0 - dm, skin_clip_deg[0]) if skin_clip_deg else sec.a0 - dm,
                    a1=min(sec.a1 + dm, skin_clip_deg[1]) if skin_clip_deg else sec.a1 + dm))
    else:
        raise ValueError(f"skin={skin!r}")
    ports = []
    r_port = SLEEVE_R_OUT_MM - 0.2
    for sl in slots:
        S.extend(sl.sectors(skin_r_in, SLEEVE_R_OUT_MM, sleeve_mat, 12))
        if feed == "ideal":
            ports.append(sl.port(r_port))
        elif feed == "castellation":
            S_feed, port = _cpw_feed(sl, BOARD_MID_Z_MM[feed_board], skin_r_in, r_port,
                                     cpw_w_mm, cpw_gap_mm, cpw_gnd_mm, sleeve_mat)
            S.extend(S_feed)
            ports.append(port)
            notes.append(f"{sl.name}: CPW feed from {feed_board} (z {BOARD_MID_Z_MM[feed_board]:.2f}) "
                         f"at {port.angle_deg:.1f}°, w {cpw_w_mm} / gap {cpw_gap_mm} mm")
        else:
            raise ValueError(f"feed={feed!r}")
    if coating_mm > 0:
        S.append(Sector("coating", "coating_ptfe", SLEEVE_R_OUT_MM, SLEEVE_R_OUT_MM + coating_mm,
                        z_lo, z_hi, priority=3))
    if housing:
        r0 = SLEEVE_R_OUT_MM + coating_mm
        S.append(Sector("housing", "pec", r0, r0 + 2.5, z_lo - 2.0, z_hi, priority=3))
        wz0, wz1, wa0, wa1 = housing["window"]
        S.append(Sector("housing_window", "air", r0, r0 + 2.5, wz0, wz1, wa0, wa1, priority=11))
    return TowerModel(S, ports, list(slots), (z_lo, z_hi), notes)


def _cpw_feed(sl: "Slot", z_board: float, r_in: float, r_port: float,
              w: float, g: float, gnd: float, gap_mat: str = "lds_lcp") -> tuple[list, Port]:
    """Coplanar feed from the radio board's castellation down/up the sleeve
    to an ARC slot: ground bands (PEC, merge with the slot patch), the CPW
    gaps (LCP), and the centre strip that crosses the slot onto its far side."""
    if sl.kind != "arc":
        raise ValueError("castellation feed is modelled for arc slots only")
    r = SLEEVE_R_OUT_MM
    deg = lambda mm: math.degrees(mm / r)
    a_f = sl.port(r_port).angle_deg
    zs = sl.z_start
    s = 1.0 if z_board > zs else -1.0              # board side of the slot
    z_near = zs + s * sl.width / 2                 # slot edge on the board side
    z_far = zs - s * (sl.width / 2 + 0.8)          # strip lands 0.8 mm past the slot
    zb_end = z_board + s * (g + 0.6)               # ground closes just past the strip end
                                                   # (kept short: another slot may sit in
                                                   # the gap on the board's far side)
    out = [
        Sector(f"{sl.name}_cpw_gnd", "pec", r_in, r, *sorted((z_near, zb_end)),
               a_f - deg(w / 2 + g + gnd), a_f + deg(w / 2 + g + gnd), priority=9),
        Sector(f"{sl.name}_cpw_gap", gap_mat, r_in, r, *sorted((z_near, z_board + s * g)),
               a_f - deg(w / 2 + g), a_f + deg(w / 2 + g), priority=10),
        Sector(f"{sl.name}_cpw_strip", "pec", r_in, r, *sorted((z_far, z_board)),
               a_f - deg(w / 2), a_f + deg(w / 2), priority=13),
    ]
    # GND castellations either side of the feed: tie both CPW ground bands to
    # the board's ground disc across the potting gap (a floating CPW ground
    # resonates on its own and swamps the slot).
    zb0, zb1 = z_board - BOARD_T_MM / 2, z_board + BOARD_T_MM / 2
    for side, sgn in (("a", -1.0), ("b", 1.0)):
        a_in, a_out = a_f + sgn * deg(w / 2 + g), a_f + sgn * deg(w / 2 + g + gnd)
        out.append(Sector(f"{sl.name}_cpw_gnd_tie_{side}", "pec", BOARD_R_MM - 0.4, r_in,
                          zb0, zb1, min(a_in, a_out), max(a_in, a_out), priority=9))
    port = Port(f"P_{sl.name}", a_f + deg(w / 2 + g / 2), r_port, z_board, "tangential", g)
    return out, port


def _offset_cylinder(name, x, y, r, z0, z1):
    # encoded as a sector with r_in < 0 marker: (x, y) stored in a0/a1.
    return Sector(name, "pec", -1.0, r, z0, z1, x, y, priority=4)


def is_offset_cylinder(s: Sector) -> bool:
    return s.r_in < 0


def slot_angles_clear_of_gnd(slots, min_deg: float = 5.0) -> bool:
    return all(abs(((s.angle_deg - g + 180) % 360) - 180) >= min_deg
               for s in slots for g in GND_CAST_ANGLES_DEG)


def model_to_dict(model: TowerModel, *, f_start_ghz: float = 1.5, f_stop_ghz: float = 2.8,
                  excite: str | None = None, mesh_mm: float = 0.4,
                  nf2ff: bool = True, ff_extra_ghz: tuple = ()) -> dict:
    """Solver-neutral JSON for openems_runner (which imports nothing from
    smash, so it runs unchanged inside the openEMS container)."""
    from smash.sim.antenna import materials as M
    used = {s.material for s in model.sectors} - {"pec"}
    return {
        "sectors": [dataclasses.asdict(s) | {"offset_cylinder": is_offset_cylinder(s)}
                    for s in model.sectors],
        "ports": [dataclasses.asdict(p) for p in model.ports],
        "slots": [dataclasses.asdict(s) for s in model.slots],
        "materials": {n: dataclasses.asdict(M.ALL[n]) for n in sorted(used)},
        "z_extent": list(model.z_extent),
        "notes": list(model.notes),
        "f_start_ghz": f_start_ghz, "f_stop_ghz": f_stop_ghz,
        "excite": excite or (model.ports[0].name if model.ports else None),
        "mesh_mm": mesh_mm, "nf2ff": nf2ff, "ff_extra_ghz": list(ff_extra_ghz),
        "r_fine_mm": SLEEVE_R_OUT_MM + 1.5,
    }
