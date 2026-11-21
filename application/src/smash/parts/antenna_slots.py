"""Sleeve slot antennas — the geometry chosen from the openEMS study
(2026-11-17, `smash.sim.antenna`, memory "antenna-sim-findings").

Each antenna is a printed ARC slot in a local copper patch on the LDS
sleeve's OUTER face, fed by a coplanar line (CPW) that runs axially from the
radio board's (wakeup) feed castellation across the slot. The patch and the
CPW grounds are GND, bonded to the boards through the flanking GND
castellations. NO copper on the sleeve's inner face in the antenna sector:
metal ~0.4 mm behind a slot shorts it (sim: S1 0–3.5 % radiated).

Simulated (C2 tower, Stycast 2651MM + Cat 11, castellation feed):
  S1  LR2021 native, ISM 2.40-2.48 GHz default + ~2.1-2.4 GHz authorised
      (DTC-tuned π): radiation 66/72/63 % at 2.15/2.30/2.44 GHz.
  (S3, BLE, merged into S1 2026-11-17: with GF30 PEEK gap rings S1 peaks at
  2.44-2.48 GHz — 50-59 % radiated — and the LR2021 + BLE share it.)
  S4  4.4-5.0 GHz transverter (2026-11-18, generate_stackup._build_transverter).
      Final rings (PEEK in S1/S4 gaps, Al from wakeup↔power down), slot ×0.9
      of the 4.4 GHz half-wave, 2 mm wide, feed 2 mm (sim C2_P_S4_p17_sc90_f20_w2):
      radiation 59/62/72/66/74 % at 4.6/4.7/4.8/4.9/5.0 GHz (50 % at 4.4);
      Zin 41+63j … 69+95j → one series ~0.5 pF gives S11 ≈ -12…-25 dB over
      4.6-5.0 GHz. Usable band 4.6-5.0 GHz (4.4-4.6 poorly matched).

Frame: PHYSICAL angles (castellations.py), z = stack height (sleeve unroll).
"""
from __future__ import annotations

import dataclasses
import math

SLEEVE_R_OUT_MM = 17.9            # 17 board + 0.1 gap + 0.8 LCP wall (sleeve_step)
BOARD_R_MM = 17.0
EPS_EFF = 2.25                    # the sim's slot-length model (cases.EPS_EFF)
PATCH_MARGIN_MM = 4.0             # local copper patch round each slot (sim skin="local")
CPW_W_MM, CPW_GAP_MM, CPW_GND_MM = 1.0, 0.5, 2.0
CPW_OVERHANG_MM = 0.8             # strip lands this far past the slot's far edge
CPW_GND_CLOSE_MM = 0.6            # CPW ground closes this far past the strip end
GND_FLANK_MM = CPW_W_MM / 2 + CPW_GAP_MM + CPW_GND_MM / 2   # GND castellation offset
# Copper stays inside the antenna sector, clear of the 105° half-shell seam
# stripe (castellations.SEAM_HALF_WIDTH_DEG = 4°) and of the signal sector
# from 255° (sim: skin_clip_deg=(109, 255)).
COPPER_SECTOR_DEG = (109.0, 255.0)
KEEPOUT_DEPTH_MM = 4.0            # board copper keep-out from the edge (sim keepout)
# Al gap rings are structural (user, 2026-11-17): open ONLY in a gap that
# holds a slot, only over that slot's span + this margin (at the ring's mean
# radius). Gaps without a slot keep a full ring.
RING_OPENING_MARGIN_MM = 2.0
RING_MEAN_R_MM = 16.5
KEEPOUT_HALFWIDTH_MM = 4.0
KEEPOUT_NEAR_MM = 1.0             # a board within this of the slot gets the keep-out


def half_wave_slot_mm(f_ghz: float, eps_eff: float = EPS_EFF) -> float:
    return 299.792458 / f_ghz / 2.0 / math.sqrt(eps_eff)


@dataclasses.dataclass(frozen=True)
class SlotAntenna:
    name: str
    net: str
    lower: str                    # board below the slot's gap
    upper: str                    # board above it
    start_deg: float              # slot START end (the feed end)
    direction: int                # +1 runs to larger angles, -1 to smaller
    f_design_ghz: float
    scale: float                  # × half-wave length (sim override S<n>_scale)
    width_mm: float
    feed_mm: float                # feed distance from the START end
    feed_board: str = "wakeup_board"
    dz_mm: float = 0.0            # axial offset from the gap mid-height (sim S<n>_dz)
    provisional: bool = False
    label: str = ""

    @property
    def length_mm(self) -> float:
        return half_wave_slot_mm(self.f_design_ghz) * self.scale

    @property
    def end_deg(self) -> float:
        return self.start_deg + self.direction * math.degrees(self.length_mm / SLEEVE_R_OUT_MM)

    @property
    def span_deg(self) -> tuple:
        return tuple(sorted((self.start_deg, self.end_deg)))

    @property
    def feed_deg(self) -> float:
        """CPW strip centre = the feed castellation angle (the sim measures the
        feed offset at its port radius, R_OUT − 0.2 mm)."""
        return self.start_deg + self.direction * math.degrees(self.feed_mm / (SLEEVE_R_OUT_MM - 0.2))

    @property
    def gnd_flank_deg(self) -> tuple:
        d = math.degrees(GND_FLANK_MM / SLEEVE_R_OUT_MM)
        return (round(self.feed_deg - d, 1), round(self.feed_deg + d, 1))


SLOTS = (
    # (2026-11-21, user) fin_ble merged into activation; the p21 layout: S1
    # moves to wakeup↔power (above its radio board, clear of S4's structure
    # that put an anti-resonance in S1's band), S4 sits in activation↔wakeup
    # 1 mm below the gap's mid-height. ⚠ S1 resonates ~2.5 GHz there and the
    # sector is full at scale 0.95 — needs end-loading to come down to LoRa.
    SlotAntenna("S1", "ANT_HF_S1", "wakeup_board", "power_board",
                start_deg=110.0, direction=+1, f_design_ghz=2.15, scale=0.95,
                width_mm=1.5, feed_mm=6.0,
                label="S1 2.4 GHz ISM: LoRa (LR2021, DTC-tuned) + BLE, shared"),
    SlotAntenna("S4", "ANT_HF_S4", "activation_interface", "wakeup_board",
                start_deg=143.0, direction=+1, f_design_ghz=4.4, scale=0.9,
                width_mm=2.0, feed_mm=2.0, dz_mm=-1.0,
                label="S4 transverter 4.6-5.0 GHz (LR2021 IF + ADF4351/LTC5549)"),
)


def by_net() -> dict:
    return {s.net: s for s in SLOTS}


def _x(theta_deg: float, theta0_deg: float) -> float:
    return SLEEVE_R_OUT_MM * math.radians((theta_deg - theta0_deg) % 360.0)


def slot_z(s: SlotAntenna, board_mid: dict) -> float:
    """Slot centre height = midway between its two boards' mid-planes (the
    sim's _gap_mid)."""
    return 0.5 * (board_mid[s.lower] + board_mid[s.upper]) + s.dz_mm


def unrolled_geometry(board_mid: dict, theta0_deg: float, z_limits: tuple) -> dict:
    """Unrolled rectangles (x0, z0, x1, z1), x = R_OUT·(θ − θ0):
      copper   — GND patch + CPW ground bands (union them),
      cutouts  — slot openings + CPW gaps (subtract from the copper),
      strips   — [(net, rect)] CPW centre strips (own net, on top),
      feeds    — [(net, x, z_board)] feed castellation via positions,
      labels   — [(text, x, z)]."""
    r = SLEEVE_R_OUT_MM
    mm = lambda deg: r * math.radians(deg)
    copper, cutouts, strips, feeds, labels = [], [], [], [], []
    zlo, zhi = z_limits
    cx0, cx1 = _x(COPPER_SECTOR_DEG[0], theta0_deg), _x(COPPER_SECTOR_DEG[0], theta0_deg) + mm(
        COPPER_SECTOR_DEG[1] - COPPER_SECTOR_DEG[0])
    for s in SLOTS:
        if s.lower not in board_mid or s.upper not in board_mid or s.feed_board not in board_mid:
            continue
        zc = slot_z(s, board_mid)
        a0, a1 = s.span_deg
        x0, x1 = _x(a0, theta0_deg), _x(a0, theta0_deg) + mm(a1 - a0)
        hw = s.width_mm / 2
        copper.append((max(x0 - PATCH_MARGIN_MM, cx0), max(zc - hw - PATCH_MARGIN_MM, zlo),
                       min(x1 + PATCH_MARGIN_MM, cx1), min(zc + hw + PATCH_MARGIN_MM, zhi)))
        cutouts.append((x0, zc - hw, x1, zc + hw))
        # CPW: from the feed board down/up to the slot (sim _cpw_feed)
        zb = board_mid[s.feed_board]
        sg = 1.0 if zb > zc else -1.0
        z_near = zc + sg * hw
        z_far = zc - sg * (hw + CPW_OVERHANG_MM)
        xf = _x(s.feed_deg, theta0_deg)
        w2, g, gnd = CPW_W_MM / 2, CPW_GAP_MM, CPW_GND_MM
        zb_end = zb + sg * (g + CPW_GND_CLOSE_MM)
        copper.append((xf - w2 - g - gnd, min(z_near, zb_end), xf + w2 + g + gnd, max(z_near, zb_end)))
        zg_end = zb + sg * g
        cutouts.append((xf - w2 - g, min(z_near, zg_end), xf + w2 + g, max(z_near, zg_end)))
        strips.append((s.net, (xf - w2, min(z_far, zb), xf + w2, max(z_far, zb))))
        feeds.append((s.net, xf, zb))
        labels.append((s.label, 0.5 * (x0 + x1), zc))          # inside the slot opening
    return {"copper": copper, "cutouts": cutouts, "strips": strips,
            "feeds": feeds, "labels": labels}


def board_keepouts(board_mid: dict, board_t_mm: float) -> list:
    """[(board, face, a0_deg, a1_deg, r_in_mm, slot)] — copper-free board-edge
    wedges behind a slot that comes within KEEPOUT_NEAR_MM of a board face
    (only the 3 mm S4 does: it fills its gap). face = the face toward the
    slot ('top' of the lower board, 'bottom' of the upper one)."""
    out = []
    hwd = math.degrees(KEEPOUT_HALFWIDTH_MM / BOARD_R_MM)
    for s in SLOTS:
        if s.lower not in board_mid or s.upper not in board_mid:
            continue
        zc = slot_z(s, board_mid)
        z0, z1 = zc - s.width_mm / 2, zc + s.width_mm / 2
        a0, a1 = s.span_deg
        for b, face in ((s.lower, "top"), (s.upper, "bottom")):
            top = board_mid[b] + board_t_mm / 2
            bot = board_mid[b] - board_t_mm / 2
            gap = (z0 - top) if face == "top" else (bot - z1)
            if gap <= KEEPOUT_NEAR_MM:
                out.append((b, face, a0 - hwd, a1 + hwd, BOARD_R_MM - KEEPOUT_DEPTH_MM, s.name))
    return out


def ring_openings(margin_mm: float = RING_OPENING_MARGIN_MM) -> dict:
    """{(lower_board, upper_board): (a0_deg, a1_deg)} — the Al ring of that
    gap is open over (a0, a1); every other gap ring is complete."""
    d = math.degrees(margin_mm / RING_MEAN_R_MM)
    out = {}
    for s in SLOTS:
        a0, a1 = s.span_deg
        k = (s.lower, s.upper)
        if k in out:
            a0, a1 = min(a0 - d, out[k][0]), max(a1 + d, out[k][1])
            out[k] = (a0, a1)
        else:
            out[k] = (a0 - d, a1 + d)
    return {k: (round(a0, 1), round(a1, 1)) for k, (a0, a1) in out.items()}
