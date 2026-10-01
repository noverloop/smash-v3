"""Per-chip solder-joint geometry from a real `Footprint`.

Used by the FEA mesh to size cohesive solder springs. Returns:

  - **`corner_reach_mm`** — the chip body's true corner-to-centre lever
    arm `√((W/2)² + (H/2)²)`. Drives the deflection at the corner ball
    (`δ_corner = κ · d² / 2`), so a bigger package means a longer arm.
    For a square chip this exceeds `max(W,H)/2` by √2 (12 mm BGA →
    8.49 mm corner reach vs 6 mm half-side); for a long thin chip it's
    only marginally larger than the long-side half-length. This is the
    geometry where the outermost ball actually sits, not the half-side.
  - **`h_joint_mm`** — the shear height of the joint (ball collapse for
    BGAs, fillet for leadless QFN/LGA, lead-bending compliance for
    gull-wing SOIC/SOT). Picked from a small `(family × pitch)` table
    keyed to the family.

Family is inferred from the footprint name + pad pattern (no SamacSys-
name regex parsing — first-principles from the real geometry):

  - BGA/CSP   = grid of small SMD round pads (≥16 pads, regular grid)
  - QFN/SON   = small SMD perimeter pads, no leads (rectangular pad shape)
  - LGA       = like QFN, name hints "lga" / "module"
  - SOIC/SOP  = gull-wing, ≤32 leads in two rows
  - SOT       = ≤6 small gull-wing leads
  - module    = single large rect package (the BLE/WiFi modules)
"""
from __future__ import annotations

import dataclasses
import math


@dataclasses.dataclass
class JointGeometry:
    family: str
    corner_reach_mm: float              # √((W/2)² + (H/2)²)
    h_joint_mm: float
    pitch_mm: float | None = None       # populated for BGA-class for clarity


def _bga_h_joint(pitch_mm: float) -> float:
    """SMTA pitch → ball-collapse height (mm)."""
    if pitch_mm <= 0.40: return 0.20
    if pitch_mm <= 0.50: return 0.25
    if pitch_mm <= 0.65: return 0.30
    if pitch_mm <= 0.80: return 0.40
    return 0.50


def _min_pitch(pads) -> float | None:
    """Minimum centre-to-centre distance between any two pads."""
    positions = [p.position_mm for p in pads if getattr(p, "position_mm", None)]
    if len(positions) < 2:
        return None
    best = float("inf")
    for i, (x1, y1) in enumerate(positions):
        for x2, y2 in positions[i + 1:]:
            d = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
            if d < best:
                best = d
    return best if best != float("inf") else None


def _is_smd_pad(p) -> bool:
    return getattr(p, "drill_mm", None) is None


def _infer_family(footprint, name_hint: str) -> str:
    """Best-effort family from name hint + pad pattern. Returns one of
    "bga", "qfn", "lga", "soic", "sop", "sot", "son", "module", or
    "unknown" (the caller skips unknown chips)."""
    nl = (name_hint or "").lower()
    for tag in ("bga", "csp", "wlcsp"):
        if tag in nl:
            return "bga"
    for tag in ("lfcsp", "qfn", "vqfn", "uqfn"):
        if tag in nl:
            return "qfn"
    if "lga" in nl:
        return "lga"
    if "module" in nl:
        return "module"
    for tag in ("soic", "sop", "tssop", "msop"):
        if tag in nl:
            return "soic"
    if nl.startswith("sot") or "sot" in nl:
        return "sot"
    if "son" in nl:
        return "son"

    # Fall back to pad-pattern heuristics if the name didn't say.
    pads = getattr(footprint, "pads", None) or []
    smd_pads = [p for p in pads if _is_smd_pad(p)]
    if not smd_pads:
        return "unknown"
    n = len(smd_pads)
    # A grid of many small round-ish pads ⇒ BGA.
    if n >= 16:
        round_pads = sum(1 for p in smd_pads
                         if getattr(p, "shape", "rect") in ("round", "circle"))
        if round_pads >= 0.7 * n:
            return "bga"
    if n <= 8:
        return "sot"
    if n <= 32:
        return "soic"
    return "qfn"


def _max_pad_dia_mm(pads) -> float:
    """Largest pad's effective diameter (max-size for SMD pads). Used to
    detect big-copper inter-board lands."""
    best = 0.0
    for p in pads or []:
        if getattr(p, "drill_mm", None) is not None:
            continue                                     # PTH — skip
        sz = getattr(p, "size_mm", None)
        if not sz:
            continue
        best = max(best, max(sz))
    return best


def joint_geometry(footprint, solder=None, *,
                   name_hint: str | None = None) -> JointGeometry | None:
    """Compute `(corner_reach, h_joint, family)` for a placed chip's
    solder joints. `solder` is currently informational (the joint heights
    here are family-driven; mixed-alloy effects are tracked at the
    FabProfile capability level, not per joint). Returns None for
    unknown packages — the caller skips them with a note in the report.

    `corner_reach` is the true corner-to-centre distance — the lever arm
    of the outermost solder ball under uniform plate curvature, not the
    longer-side half-length. For a 12 × 12 BGA this is √72 ≈ 8.49 mm,
    not 6 mm; for a 9 × 13 it's √(20.25 + 42.25) ≈ 7.91 mm, not 6.5 mm.
    The half-side formula previously here under-estimated corner strain
    by up to √2 on square packages."""
    if footprint is None:
        return None
    size = getattr(footprint, "size_mm", None)
    if not size:
        return None
    w, h = size
    corner_reach = math.sqrt((w / 2.0) ** 2 + (h / 2.0) ** 2)

    family = _infer_family(footprint, name_hint or getattr(footprint, "name", ""))
    if family == "unknown":
        return None

    pads = getattr(footprint, "pads", None) or []
    pitch = _min_pitch(pads)

    # ── inter-board copper-land connectors (J_*, P_*, "Pogo"...) ─────
    # These aren't chip packages — they're copper pads the next tile
    # solders directly onto. The joint volume scales with pad diameter
    # (a 2 mm pogo-style land carries far more solder than a 1 mm LGA
    # ball), so h_joint is derived from the pad, not the chip family.
    # Rule of thumb: solder bump / fillet height ≈ 20 % of pad Ø.
    max_pad = _max_pad_dia_mm(pads)
    nl = (name_hint or "").lower()
    looks_inter_board = (
        max_pad >= 1.5                                   # genuinely big land
        or "pogo" in nl
        or "payload" in nl                               # LGA-24_*Payload_*
    )
    if looks_inter_board and max_pad > 0:
        return JointGeometry(family="copper_pad", corner_reach_mm=corner_reach,
                             h_joint_mm=max(0.15, 0.2 * max_pad),
                             pitch_mm=pitch)

    if family == "bga":
        return JointGeometry(family="bga", corner_reach_mm=corner_reach,
                             h_joint_mm=_bga_h_joint(pitch or 0.5),
                             pitch_mm=pitch)
    h_joint = {
        "qfn":    0.08,
        "son":    0.08,
        "lga":    0.10,
        "soic":   0.20,
        "sop":    0.20,
        "sot":    0.15,
        "module": 0.30,
    }[family]
    return JointGeometry(family=family, corner_reach_mm=corner_reach,
                         h_joint_mm=h_joint, pitch_mm=pitch)
