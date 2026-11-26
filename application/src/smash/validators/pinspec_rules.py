"""Datasheet rules from the pinspecs, checked against the netlist.

  P1 connect    a pin's datasheet connection rule (pinspec "connect" field):
                  "gnd"          on a ground net
                  "supply"       on a power rail (any)
                  "open"         not connected (or alone on its net)
                  "open_or_gnd"  not connected, or on ground
                  "defined"      not floating: the net has something besides this pin
                  "same_as:<n>"  on the same net as pin <n> of the same part
  P2 supply     a power pin with voltage_range_v sits on a rail inside it
  P3 unconnected a non-output pin with no net (or alone on its net) is allowed to float
                  by the datasheet: nc type, or a connect / "unused" rule of
                  "open" / "open_or_gnd"; otherwise the "unused" rule is reported
  P4 abs max    a pin's highest static voltage stays inside its datasheet absolute
                  maximum ratings (pinspec fields, all in volts):
                    "max_v"     vs GND
                    "max_v_to"  {"<pin>": v}  |V(this) − V(that pin)| ≤ v, or
                                {"<pin>": [lo, hi]}  lo ≤ V(this) − V(that) ≤ hi
                                (FET V_GS / V_DS, diode V_R, differential limits)
                    "max_over"  {"pin": "<supply pin>", "v": 0.3}
                                V(this) ≤ V(supply) + v while both are known
                  A net's voltage is its rail's voltage_v (through 0 Ω / beads);
                  a non-rail net takes the divider voltage of its resistors to
                  rails / GND, or the highest rail it is pulled up to. Static
                  only: transients, ringing and unpowered-domain back-feed are
                  outside this rule.

`check(design)` returns [(rule, ref, pin, message)]. Accepted exceptions live
in pinspec_rules_acknowledged.json next to this file ("<rule> <ref>.<pin>").
"""
from __future__ import annotations

import json
import re
from pathlib import Path

GND_RX = re.compile(r"(^|_)GND($|_)|^FLEX_GND$|^GND", re.I)


def _net(p):
    n = p.net
    return getattr(n, "name", n)


def acknowledged() -> dict:
    f = Path(__file__).with_name("pinspec_rules_acknowledged.json")
    return json.loads(f.read_text()) if f.exists() else {}


def check(design) -> list:
    from smash.parts._pinspec import load_pinspec, _sources_root      # noqa: F401
    from smash.validators.electrical import net_voltages
    volts = net_voltages(design)
    members: dict = {}
    for c in design.chips:
        for p in c.pins:
            n = _net(p)
            if n:
                members.setdefault(n, []).append((c.ref, p.num))
    vmax = _signal_voltages(design, volts)
    raw_cache: dict = {}
    out = []
    for c in design.chips:
        if not c.manf_pn:
            continue
        spec = load_pinspec(c.manf_pn)
        if spec is None:
            continue
        raw = raw_cache.get(c.manf_pn)
        if raw is None:
            raw = raw_cache[c.manf_pn] = _raw_pins(c.manf_pn)
        by_num = {str(p.num).removeprefix("BALL_"): p for p in c.pins}
        for sp in spec.pins:
            p = by_num.get(sp.num)
            if p is None:
                continue
            net = _net(p)
            rule = (raw.get(sp.num) or {}).get("connect")
            alone = net is None or len(members.get(net, [])) <= 1
            is_gnd = bool(net and GND_RX.search(net))
            is_rail = bool(net and (volts.get(net) is not None or is_gnd))
            # P1
            if rule:
                bad = None
                if rule == "gnd" and not is_gnd:
                    bad = f"must be on GND, is on {net}"
                elif rule == "supply" and not (net and volts.get(net) is not None):
                    bad = f"must be on a supply rail, is on {net}"
                elif rule == "open" and not alone:
                    bad = f"must be left open, is on {net}"
                elif rule == "open_or_gnd" and not (alone or is_gnd):
                    bad = f"must be open or GND, is on {net}"
                elif rule == "defined" and alone:
                    bad = "must not float, has no connection"
                elif rule.startswith("same_as:"):
                    other = by_num.get(rule.split(":", 1)[1])
                    unused = (raw.get(sp.num) or {}).get("unused")
                    both_open = net is None and other is not None and _net(other) is None
                    if both_open and unused in ("open", "open_or_gnd"):
                        pass                                  # unused pair, both left open
                    elif other is None or _net(other) != net or net is None:
                        bad = f"must share a net with pin {rule.split(':', 1)[1]} ({_net(other) if other else '?'}), is on {net}"
                if bad:
                    out.append(("P1", c.ref, sp.num, f"{sp.name}: {bad}"))
            # P2
            if sp.type == "power" and sp.voltage_range_v and net and volts.get(net) is not None:
                lo, hi = sp.voltage_range_v
                v = volts[net]
                if not (lo - 1e-6 <= v <= hi + 1e-6):
                    out.append(("P2", c.ref, sp.num,
                                f"{sp.name} on {net} = {v:g} V, datasheet {lo:g}–{hi:g} V"))
            # P3 — an unconnected pin must be allowed to float by the datasheet:
            # NC type, connect open/open_or_gnd, or unused open/open_or_gnd
            unused = (raw.get(sp.num) or {}).get("unused")
            if alone and sp.type not in ("nc", "no_connect", "output") \
                    and rule not in ("open", "open_or_gnd") and unused not in ("open", "open_or_gnd"):
                why = f" (datasheet when unused: {unused})" if unused else ""
                out.append(("P3", c.ref, sp.num, f"{sp.name} ({sp.type}) is unconnected{why}"))
            # P4 — absolute maximum ratings
            rp = raw.get(sp.num) or {}
            v_here = vmax.get(net) if net else None
            mv = rp.get("max_v")
            if isinstance(mv, (int, float)) and v_here is not None and v_here > mv + 1e-6:
                out.append(("P4", c.ref, sp.num,
                            f"{sp.name} on {net} reaches {v_here:g} V > abs max {mv:g} V"))
            for other, lim in (rp.get("max_v_to") or {}).items():
                op = _pin_by_key(c, by_num, other)
                onet = _net(op) if op is not None else None
                if v_here is None or onet is None or vmax.get(onet) is None:
                    continue
                dv = v_here - vmax[onet]
                lo, hi = (lim if isinstance(lim, (list, tuple)) else (-lim, lim))
                if dv > hi + 1e-6 or dv < lo - 1e-6:
                    out.append(("P4", c.ref, sp.num,
                                f"{sp.name} on {net} ({v_here:g} V) vs {other} on {onet} "
                                f"({vmax[onet]:g} V): {dv:+g} V outside abs max {lo:g}…{hi:g} V"))
            mo = rp.get("max_over")
            if mo and v_here is not None:
                op = _pin_by_key(c, by_num, mo.get("pin"))
                onet = _net(op) if op is not None else None
                if onet in volts and v_here > volts[onet] + mo.get("v", 0.3) + 1e-6:
                    out.append(("P4", c.ref, sp.num,
                                f"{sp.name} on {net} reaches {v_here:g} V > {mo.get('pin')} "
                                f"({volts[onet]:g} V) + {mo.get('v', 0.3):g} V"))
    return out


def _pin_by_key(chip, by_num, key):
    """A pin of `chip` by number or name."""
    if key is None:
        return None
    k = str(key)
    if k in by_num:
        return by_num[k]
    return next((p for p in chip.pins if str(p.name or "").upper() == k.upper()), None)


def _signal_voltages(design, volts) -> dict:
    """{net: highest static voltage}: rails as given; a non-rail net with
    resistors to known nets takes their Thevenin voltage when it has a path to
    GND through a resistor (a divider), else the highest rail it is pulled to."""
    from smash.validators.electrical import RAIL_TOL
    volts = {n: v * (1 + RAIL_TOL) for n, v in volts.items()}     # rail upper tolerance
    out = dict(volts)
    res: dict = {}
    for c in design.chips:
        if not c.ref.startswith("R") or len(c.pins) != 2:
            continue
        ohms = _ohms(getattr(c, "value", None))
        a, b = (_net(p) for p in c.pins)
        if not a or not b or ohms is None:
            continue
        res.setdefault(a, []).append((b, ohms))
        res.setdefault(b, []).append((a, ohms))
    for net, links in res.items():
        if net in volts:
            continue
        known = [(volts[o], r) for o, r in links if o in volts]
        if not known:
            continue
        if any(v == 0.0 for v, _ in known) and any(v > 0 for v, _ in known):
            g = sum(1 / max(r, 1e-3) for _, r in known)
            out[net] = round(sum(v / max(r, 1e-3) for v, r in known) / g, 4)
        else:
            out[net] = max(v for v, _ in known)
    return out


_MULT = {"": 1, "R": 1, "K": 1e3, "M": 1e6, "G": 1e9}


def _ohms(value):
    s = str(value or "").strip().upper().replace("Ω", "").replace("OHM", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([RKMG]?)(\d*)", s)
    if not m:
        return None
    base = float(m.group(1) + ("." + m.group(3) if m.group(3) else ""))
    return base * _MULT[m.group(2)]


def _raw_pins(manf_pn: str) -> dict:
    """pin num → raw pinspec dict (for fields the PinSpec dataclass drops)."""
    from smash.parts import _pinspec as P
    root = P._sources_root()
    for cand in (manf_pn, manf_pn.replace(":", "_"), manf_pn.replace("/", "_"),
                 re.sub(r"[/#,: ()+]", "_", manf_pn)):
        f = root / cand / "pinspec.json"
        if f.is_file():
            return {str(p["num"]): p for p in json.loads(f.read_text())["pins"]}
    return {}


def report(design) -> list:
    ack = acknowledged()
    return [f for f in check(design) if f"{f[0]} {f[1]}.{f[2]}" not in ack]
