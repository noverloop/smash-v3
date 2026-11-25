"""Decoupling map: every IC supply rail → its capacitors, where they sit
relative to the pin they serve, and the placement rule each must meet.

Source of truth is `Chip.decouples` (set by `cap_to_gnd(pin=...)` and the
explicit factories): [(ic_ref, pin num | name | None)]. Distances are
measured on the current (pre-layout) placement, pad centre to cap centre,
so the table doubles as a checklist for the layout EE:

  * ≤ 220 nF (high-frequency)  → ≤ 1.5 mm from its pin, same face, or
    directly under the BGA on the opposite face (via-in-pad);
  * 0.47 - 4.7 µF               → ≤ 3 mm;
  * ≥ 10 µF (bulk)              → ≤ 6 mm from the IC body.

Output: DECOUPLING_MAP.csv (one row per cap) + per-IC rail coverage
(power pins on a rail with no assigned cap are flagged).
"""
from __future__ import annotations

import csv
import math
import pathlib

from smash.layout.placer.grid import world_pad_position


# enable / mode straps tied to a rail are logic inputs, not supply pins
_LOGIC_TIE = __import__("re").compile(r"^(EN|MODE|ON/OFF|CE|SD|SHDN|NSLEEP|STBY)\b", __import__("re").I)


def _limit_mm(farads: float | None) -> float:
    if farads is None:
        return 3.0
    if farads <= 0.221e-6:
        return 1.5
    if farads < 9e-6:
        return 3.0
    return 6.0


def _placements(boards) -> dict:
    out = {}
    for name, b in boards.items():
        for p in getattr(b, "chip_placements", None) or []:
            ref = getattr(p.item, "ref", None)
            if ref:
                out[ref] = (name, p)
    return out


def _pad_xy(placement, chip, pin_key):
    fp = chip.footprint
    if fp is None:
        return None
    pins = {str(p.num): p for p in chip.pins}
    by_name = {str(p.name).upper(): p for p in chip.pins if p.name}
    pin = pins.get(str(pin_key)) or by_name.get(str(pin_key).upper()) if pin_key is not None else None
    pads = [pd for pd in fp.pads if pin is None or str(pd.num) == str(pin.num)]
    if not pads:
        return None
    xs = [world_pad_position(placement, pd) for pd in pads]
    if pin is None:      # whole chip: its centre
        return placement.position_mm
    return min(xs, key=lambda q: math.dist(q, placement.position_mm))


def decoupling_map(d, boards) -> tuple[list[dict], list[dict]]:
    """(rows, gaps). rows: one per cap with a decouples target; gaps: IC
    supply rails with power pins but no assigned capacitor."""
    chips = {c.ref: c for c in d.chips}
    place = _placements(boards)
    pin_net = {}
    for n in d.nets:
        for ref, num in n.pins:
            pin_net[(ref, str(num))] = n
    rows = []
    covered: set = set()      # (ic, net)
    for c in d.chips:
        if c.dnp or not getattr(c, "decouples", None) or not c.ref.startswith("C"):
            continue
        cnet = next((pin_net.get((c.ref, str(p.num))) for p in c.pins
                     if pin_net.get((c.ref, str(p.num))) is not None
                     and pin_net[(c.ref, str(p.num))].kind != "ground"), None)
        for ic_ref, pin_key in c.decouples:
            ic = chips.get(ic_ref)
            if ic is None:
                continue
            covered.add((ic_ref, cnet.name if cnet else None))
            dist = None
            same_face = None
            if ic_ref in place and c.ref in place:
                (b_ic, p_ic), (b_c, p_c) = place[ic_ref], place[c.ref]
                if b_ic == b_c:
                    xy = _pad_xy(p_ic, ic, pin_key)
                    if xy is not None:
                        dist = math.dist(xy, p_c.position_mm)
                        same_face = p_ic.face == p_c.face
            lim = _limit_mm(getattr(c, "capacitance_f", None))
            if pin_key is None and dist is not None:
                # body-level target: distance to the nearest body edge
                fw, fh = (ic.size_mm or (0, 0))[:2]
                dist = max(0.0, dist - max(fw, fh) / 2)
            status = ("not placed" if dist is None else
                      "ok" if dist <= lim else "far")
            rows.append(dict(cap=c.ref, value=c.value, part=c.manf_pn, rail=cnet.name if cnet else "",
                             ic=ic_ref, pin=pin_key if pin_key is not None else "(body)",
                             board=c.board_tag, cap_face=place.get(c.ref, (None, None))[1].face
                             if c.ref in place else "",
                             same_face="" if same_face is None else ("yes" if same_face else "no"),
                             dist_mm="" if dist is None else f"{dist:.2f}", limit_mm=f"{lim:.1f}",
                             status=status))
    gaps = []
    for ic in d.chips:
        if not ic.ref.startswith("U_") or ic.dnp:
            continue
        rails = {}
        for p in ic.pins:
            n = pin_net.get((ic.ref, str(p.num)))
            if n is not None and n.kind == "power" and not _LOGIC_TIE.match(str(p.name or "")):
                rails.setdefault(n.name, []).append(str(p.name or p.num))
        for rail, pins in rails.items():
            if (ic.ref, rail) not in covered:
                gaps.append(dict(ic=ic.ref, part=ic.manf_pn, rail=rail, pins=" ".join(pins[:8])))
    return rows, gaps


def write(d, boards, out_dir) -> dict:
    out_dir = pathlib.Path(out_dir)
    rows, gaps = decoupling_map(d, boards)
    with open(out_dir / "DECOUPLING_MAP.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["cap"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["board"], r["ic"], r["rail"], r["cap"])))
    with open(out_dir / "DECOUPLING_GAPS.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ic", "part", "rail", "pins"])
        w.writeheader()
        w.writerows(sorted(gaps, key=lambda r: (r["ic"], r["rail"])))
    st = {}
    for r in rows:
        st[r["status"]] = st.get(r["status"], 0) + 1
    return {"caps": len(rows), "status": st, "rails_without_cap": len(gaps)}
