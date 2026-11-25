"""Netlist audits driven by the datasheet pinspecs (+ a power-state model).

  D1 levels      a driver's I/O-domain voltage exceeds what a receiving pin
                 tolerates (pin "max_v", else its domain supply + 0.3 V)
  D2 back-power  in a power state, a powered driver / pull-up reaches a pin
                 whose own I/O supply is off (current flows through its
                 clamp into the dead rail)
  S1 straps      worst-case level of a strap / enable net (external pulls +
                 the pins' internal pulls) against the pins' VIH / VIL
  O1 open-drain  an open-drain output with no pull-up on its net
  H1 height      a part's modelled height is below its datasheet maximum
  R1 budget      per-rail current estimate vs the source's rating (report)

Pin facts come from the pinspec fields `io_domain`, `max_v`, `open_drain`,
`internal_pull`, `vih` / `vil` and `_meta.height_max_mm`; STM32 domains are
encoded here (every GPIO on its VDD bank — all banks of this design are on
the part's main I/O rail — ADC inputs limited to their reference).
Findings are (rule, where, message); accepted ones live in
audits_acknowledged.json ("<rule> <where>").
"""
from __future__ import annotations

import json
import re
from pathlib import Path

GND_RX = re.compile(r"(^|_)GND($|_)|^GND", re.I)

# ── power-state model: rails that are ON in each state (cumulative) ─────────
_SHELF = {"BAT_RAW", "TMR_VDD"}
_AON = _SHELF | {"BAT_PROT", "3V3_AON", "WBA_VDD11"}
_MAIN = _AON | {"REG_IN_MAIN"}
# 3V3 is a buck off COMP_5V_RAW: it rises with the 5 V boost
_PMIC_IN = _MAIN | {"COMP_5V_RAW", "COMP_BST_VCC", "COMP_5V", "3V3", "LR_VBAT", "LR_VDCC",
                    "LR_VPAX", "LR_VR_PA", "LR_VTCXO", "LR_TCXO_3V3", "XV_LO_3V3", "MAG_1V8"}
_RANK1 = _PMIC_IN | {"COMP_3V3", "COMP_1V8_AON"}
_RANK3 = _RANK1 | {"COMP_0V82", "COMP_0V9", "COMP_1V8"}
_RUN = _RANK3 | {"COMP_1V35", "COMP_2V8", "CAM_VAA_2V8", "CAM_VCORE_1V15", "AWR_1V2", "AWR_1V3",
                 "AWR_1V8", "AWR_1V0", "XV_5V", "XV_PA_VDD1", "ACTIVATE_HV"}
POWER_STATES = {"shelf": _SHELF, "aon": _AON, "main": _MAIN, "pmic_input": _PMIC_IN,
                "pmic_rank1": _RANK1, "pmic_rank3": _RANK3, "run": _RUN}
# main → pmic_rank3 last ~10 ms at every power-up: COMP_BOOST_SD is pulled up to
# REG_IN_MAIN, so the COMP boost and the PMIC (AUTO_TURN_ON) start with the main
# switch. Back-feed there is the accepted start-up transient; D2 gates on the
# lasting states only (the transient ones are reported by `transient()`).
LASTING_STATES = ("shelf", "aon", "run")
PASSTHROUGH_PNS = {"SN74CB3T3125PWR"}           # FET bus switches: pass-through, not drivers
EXTERNAL_RAILS = {"DEV_VBUS", "DEV_3V3", "EXT_VIN"}     # dev bench / probe: always on

# source rail → (regulator ref, rated output mA) for the budget report
RAIL_SOURCES = {
    "3V3_AON": ("U_AON_LDO", 100), "TMR_VDD": ("U_TMR_LDO", 100), "MAG_1V8": ("U_MAG_LDO", 100),
    "3V3": ("U_PWR", 2000),
    "COMP_3V3": ("U_PMIC BUCK4", 500), "COMP_1V8": ("U_PMIC BUCK5", 500),
    "COMP_0V82": ("U_PMIC BUCK2", 2000), "COMP_0V9": ("U_PMIC BUCK1", 1000),
    "COMP_1V8_AON": ("U_PMIC LDO1", 20), "COMP_1V35": ("U_PMIC BUCK6", 2500),
    "AWR_1V2": ("U_AWR_BUCK12", 2000), "AWR_1V8": ("U_AWR_LDO18", 2000), "AWR_1V3": ("U_AWR_BUCK13", 3000),
    "XV_5V": ("Q_XV_PA_SW", 2000), "DEV_3V3": ("U_DEV_LDO", 1200),
}


def _net(p):
    n = p.net
    return getattr(n, "name", n)


def _raw(manf_pn):
    from smash.validators.pinspec_rules import _raw_pins
    return _raw_pins(manf_pn) if manf_pn else {}


def _meta(manf_pn) -> dict:
    from smash.parts import _pinspec as P
    root = P._sources_root()
    for cand in (manf_pn, manf_pn.replace(":", "_"), manf_pn.replace("/", "_"),
                 re.sub(r"[/#,: ()+]", "_", manf_pn)):
        f = root / cand / "pinspec.json"
        if f.is_file():
            return json.loads(f.read_text()).get("_meta", {})
    return {}


class _Model:
    """Per-pin I/O domain rail, tolerance and roles, built once per design."""

    def __init__(self, design):
        from smash.validators.electrical import net_voltages
        self.d = design
        self.volts = net_voltages(design)
        self.kind = {n.name: n.kind for n in design.nets}
        self.members: dict = {}
        for c in design.chips:
            for p in c.pins:
                if _net(p):
                    self.members.setdefault(_net(p), []).append((c, p))
        self.raw = {c.ref: _raw(c.manf_pn) for c in design.chips}
        # STM32MP25 strap facts (DS14285: BOOT0..3 "TTPD", RPD 30/40/50 kΩ,
        # VIH 0.7·VDD / VIL 0.3·VDD, Table 61) — the MP25 has no pinspec.
        for c in design.chips:
            if (c.manf_pn or "").startswith("STM32MP"):
                for p in c.pins:
                    if re.fullmatch(r"BOOT[0-3]", p.name or ""):
                        self.raw[c.ref].setdefault(str(p.num), {}).update(
                            internal_pull={"dir": "down", "kohm": [30, 50]},
                            vih=[0.7, "frac"], vil=[0.3, "frac"], type="input")

    def is_rail(self, net):
        return bool(net) and (self.kind.get(net) in ("power", "ground") or GND_RX.search(net))

    def domain_rail(self, c, p) -> str | None:
        """Net name of the supply that sets this pin's I/O level."""
        pn = c.manf_pn or ""
        if pn.startswith("STM32"):
            if pn.startswith("STM32MP"):
                if p.name in ("OSC_IN", "OSC_OUT") or p.name.startswith("ANA"):
                    return "COMP_1V8_AON"
                return "COMP_3V3"
            vdd = next((q for q in c.pins if re.fullmatch(r"VDD(_\d+)?", q.name or "") and _net(q)), None)
            return _net(vdd) if vdd else None
        rp = self.raw.get(c.ref, {}).get(str(p.num), {})
        if rp.get("io_domain"):
            sup = next((q for q in c.pins if str(q.num) == str(rp["io_domain"])), None)
            return _net(sup) if sup else None
        sups = {_net(q) for q in c.pins if self.ptype(c, q) == "power" and _net(q) and not GND_RX.search(_net(q))}
        return next(iter(sups)) if len(sups) == 1 else None

    _RF = re.compile(r"(^|[_/])(RF|ANT|IF|LO|CLK[PM])|RFIN|RFOUT|^RF", re.I)

    def ptype(self, c, p) -> str:
        """Pin type: the datasheet pinspec's when the part definition has none;
        STM32 GPIO balls are I/O. RF / antenna / IF / LO pins carry AC behind
        DC blocks — not logic drivers or receivers."""
        if self._RF.search(p.name or ""):
            return "rf"
        if (c.manf_pn or "") in PASSTHROUGH_PNS or c.ref.startswith("J_"):
            return "passive"                     # switches / connectors: no driving supply
        if (c.manf_pn or "").startswith("STM32") and re.match(r"P[A-Z]\d", p.name or ""):
            return "io"
        if p.type:
            return p.type
        return (self.raw.get(c.ref, {}).get(str(p.num), {}) or {}).get("type") or ""

    def max_v(self, c, p) -> float | None:
        rp = self.raw.get(c.ref, {}).get(str(p.num), {})
        if rp.get("max_v") is not None:
            return float(rp["max_v"])
        if (c.manf_pn or "").startswith("STM32MP") and self._is_adc(c, p):
            return (self.volts.get("COMP_1V8") or 1.8) + 0.3          # VREF+ = VDDA18ADC
        dom = self.domain_rail(c, p)
        v = self.volts.get(dom) if dom else None
        return None if v is None else v + 0.3

    def _is_adc(self, c, p):
        from smash.validators.stm32_functions import FUNCTIONS
        rx = FUNCTIONS.get(c.ref, {}).get(_net(p) or "", "")
        return rx.startswith("ADC")

    def drives(self, c, p):
        return self.ptype(c, p) in ("output", "io") and not self.raw.get(c.ref, {}).get(str(p.num), {}).get("open_drain")

    def receives(self, c, p):
        return self.ptype(c, p) in ("input", "io", "analog")

    def pullups(self, net):
        """[(resistor ref, rail)] — 2-pin resistors from this net to a supply rail.
        A net that also has a resistor to ground is a divider, not a pull-up:
        its level is set by the ratio, so it is left out (no false over-voltage)."""
        to_gnd = any(c.ref.startswith("R") and len(c.pins) == 2 and
                     GND_RX.search(_net(next(q for q in c.pins if q is not p)) or "-")
                     for c, p in self.members.get(net, []))
        if to_gnd:
            return []
        out = []
        for c, p in self.members.get(net, []):
            if not c.ref.startswith("R") or len(c.pins) != 2:
                continue
            other = next(q for q in c.pins if q is not p)
            on = _net(other)
            if on and self.kind.get(on) == "power":
                out.append((c.ref, on))
        return out


def check(design, states=LASTING_STATES) -> list:
    m = _Model(design)
    out = []
    signal_nets = [n for n in m.members if not m.is_rail(n)]
    for net in signal_nets:
        mem = m.members[net]
        chips = [(c, p) for c, p in mem if not re.match(r"(R|C|L|FB|TP|J_CAST|FID)", c.ref)]
        drivers = [(c, p, m.domain_rail(c, p)) for c, p in chips if m.drives(c, p)]
        pulls = m.pullups(net)
        rx = [(c, p) for c, p in chips if m.receives(c, p)]
        # D1 levels
        srcs = [(f"{c.ref}.{p.num}", r) for c, p, r in drivers if r] + [(rr, rail) for rr, rail in pulls]
        for c, p in rx:
            lim = m.max_v(c, p)
            if lim is None:
                continue
            for who, rail in srcs:
                if who.startswith(c.ref + "."):
                    continue
                v = m.volts.get(rail)
                if v is not None and v > lim + 0.05:
                    out.append(("D1", f"{c.ref}.{p.num}",
                                f"{net}: {who} at {v:g} V ({rail}) into {c.ref}.{p.num} {p.name} (max {lim:g} V)"))
        # D2 back-power
        for state, on in POWER_STATES.items():
            if state not in states:
                continue
            on = on | EXTERNAL_RAILS
            live = [(who, rail) for who, rail in srcs if rail in on]
            if not live:
                continue
            for c, p in rx:
                dom = m.domain_rail(c, p)
                rp = m.raw.get(c.ref, {}).get(str(p.num), {})
                if rp.get("max_v") is not None and m.ptype(c, p) in ("input", "io"):
                    continue                     # rated independent of its supply (fail-safe input)
                if dom and m.kind.get(dom) == "power" and dom not in on:
                    who, rail = live[0]
                    if who.startswith(c.ref + "."):
                        continue
                    out.append(("D2", f"{c.ref}.{p.num}@{state}",
                                f"{net}: {who} ({rail} on) drives {c.ref}.{p.num} {p.name} whose supply {dom} is off"))
                    break
        # O1 open-drain
        for c, p in chips:
            if m.raw.get(c.ref, {}).get(str(p.num), {}).get("open_drain") and not pulls:
                internal_up = any((m.raw.get(c2.ref, {}).get(str(p2.num), {}).get("internal_pull") or {}).get("dir") == "up"
                                  for c2, p2 in chips)
                if not internal_up and len(mem) > 1:
                    out.append(("O1", f"{c.ref}.{p.num}", f"{net}: open-drain {c.ref}.{p.num} {p.name} has no pull-up"))
        # S1 straps
        out += _straps(m, net, chips, pulls)
    # H1 height
    for c in design.chips:
        hmax = _meta(c.manf_pn).get("height_max_mm") if c.manf_pn else None
        if hmax and c.height_mm is not None and c.height_mm + 1e-6 < float(hmax):
            out.append(("H1", c.ref, f"{c.manf_pn}: modelled {c.height_mm} mm < datasheet max {hmax} mm"))
    return out


def _straps(m, net, chips, pulls):
    spec_pins = [(c, p, m.raw.get(c.ref, {}).get(str(p.num), {})) for c, p in chips]
    spec_pins = [(c, p, rp) for c, p, rp in spec_pins if rp.get("vih") or rp.get("vil")]
    if not spec_pins or any(m.drives(c, p) for c, p in chips):
        return []
    # resistor network: (R ohm, V) branches; tolerances 1 % external, internal min..max
    branches_lo, branches_hi = [], []
    for rr, rail in pulls:
        r = _r_ohm(m, rr)
        v = m.volts.get(rail)
        if r and v is not None:
            branches_lo.append((r, v)); branches_hi.append((r, v))
    for c, p in chips:
        if not c.ref.startswith("R") or len(c.pins) != 2:
            continue
        other = next(q for q in c.pins if q is not p)
        if _net(other) and GND_RX.search(_net(other)):
            r = _r_ohm(m, c.ref)
            if r:
                branches_lo.append((r, 0.0)); branches_hi.append((r, 0.0))
    for c, p, rp in spec_pins:
        ip = rp.get("internal_pull")
        if ip:
            lo_k, hi_k = ip["kohm"]
            dom = m.volts.get(m.domain_rail(c, p) or "", 3.3)
            v = dom if ip["dir"] == "up" else 0.0
            # worst case for the LOW bound: strong pull-downs / weak pull-ups
            branches_lo.append(((lo_k if v == 0 else hi_k) * 1e3, v))
            branches_hi.append(((hi_k if v == 0 else lo_k) * 1e3, v))
    if not branches_lo:
        return []
    def thev(br):
        g = sum(1 / r for r, _ in br)
        return sum(v / r for r, v in br) / g
    vmin, vmax = sorted((thev(branches_lo), thev(branches_hi)))
    out = []
    for c, p, rp in spec_pins:
        dom = m.volts.get(m.domain_rail(c, p) or "", 3.3)
        def th(key):
            t = rp.get(key)
            return None if not t else (t[0] * dom if t[1] == "frac" else t[0])
        vih, vil = th("vih"), th("vil")
        nominal = (vmin + vmax) / 2
        if vih is not None and nominal > dom / 2 and vmin < vih:
            out.append(("S1", f"{c.ref}.{p.num}", f"{net}: high level {vmin:.2f}–{vmax:.2f} V below VIH {vih:.2f} V ({p.name})"))
        if vil is not None and nominal <= dom / 2 and vmax > vil:
            out.append(("S1", f"{c.ref}.{p.num}", f"{net}: low level {vmin:.2f}–{vmax:.2f} V above VIL {vil:.2f} V ({p.name})"))
    return out


def _r_ohm(m, ref):
    c = m.d.chip_by_ref(ref)
    from smash.parts._passives_util import parse_resistance_ohm
    try:
        return parse_resistance_ohm(str(getattr(c, "value", "") or ""))
    except Exception:
        return None


def transient(design) -> list:
    """D2 findings in the ~10 ms start-up states only (report, not a gate)."""
    lasting = {f[1] for f in check(design)}
    return [f for f in check(design, states=tuple(POWER_STATES)) if f[0] == "D2" and f[1] not in lasting]


def budget(design) -> list:
    """[(rail, source, rated mA, estimated mA, unknown loads)] — per-chip current
    = p_active_w / rail V for single-supply parts; multi-rail parts are listed
    as unknown unless their p_active_w is on one rail only."""
    m = _Model(design)
    rows = []
    for rail, (src, rated) in RAIL_SOURCES.items():
        v = m.volts.get(rail)
        est, unknown = 0.0, []
        seen = set()
        for c, p in m.members.get(rail, []):
            if c.ref in seen or c.ref.startswith(("R", "C", "L", "FB", "TP")) or c.ref == src.split()[0]:
                continue
            seen.add(c.ref)
            sups = {_net(q) for q in c.pins if q.type == "power" and _net(q) and not GND_RX.search(_net(q))}
            if (p.type == "power") and len(sups) == 1 and getattr(c, "p_active_w", None) and v:
                est += c.p_active_w / v * 1e3
            elif p.type == "power":
                unknown.append(c.ref)
        rows.append((rail, src, rated, round(est), unknown))
    return rows


def acknowledged() -> dict:
    f = Path(__file__).with_name("audits_acknowledged.json")
    return json.loads(f.read_text()) if f.exists() else {}


def report(design) -> list:
    ack = acknowledged()
    return [f for f in check(design) if f"{f[0]} {f[1]}" not in ack]


# ── ratings / standby / environment ────────────────────────────────────────

PRODUCT_TEMP_C = (-40, 85)          # required operating range (all fitted tower parts)
STANDBY_BUDGET_UA = 28.0            # 'aon' state budget (battery sim, Standby)
_CASE_MM3 = {"0201": 0.6 * 0.3 * 0.3, "0402": 1.0 * 0.5 * 0.5, "0603": 1.6 * 0.8 * 0.8,
             "0805": 2.0 * 1.25 * 1.25, "1206": 3.2 * 1.6 * 1.6, "1210": 3.2 * 2.5 * 2.5}


def _two_nets(c):
    return [_net(p) for p in c.pins]


def resistor_power(design) -> list:
    """R2: static dissipation V²/R of every resistor whose both ends sit on
    known rails, or between a rail and a signal (worst case: the signal held
    at the other extreme). (rule, ref, message) when > 50 % of the rating."""
    m = _Model(design)
    out = []
    for c in design.chips:
        if not c.ref.startswith("R") or len(c.pins) != 2 or c.dnp:
            continue
        r = _r_ohm(m, c.ref)
        rating = getattr(c, "power_rating_w", None) or 0.063
        if not r:
            continue
        a, b = _two_nets(c)
        va = 0.0 if (a and GND_RX.search(a)) else m.volts.get(a)
        vb = 0.0 if (b and GND_RX.search(b)) else m.volts.get(b)
        if va is None and vb is None:
            continue
        if va is None or vb is None:
            if r < 1e3:
                continue                               # series / RF / power-path element: needs its operating current
            v = va if va is not None else vb           # pull-up: worst case the line held at 0 V
            kind = "pull-up, line held low"
        else:
            v = abs(va - vb); kind = "rail→rail"
        p = v * v / r
        if p > 0.5 * rating:
            out.append(("R2", c.ref, f"{c.value} {kind}: {p*1e3:.0f} mW of {rating*1e3:.0f} mW ({a} / {b})"))
    return out


def mlcc_bias(design) -> list:
    """C1 (estimate): Class-II MLCC capacitance left at its DC bias. Loss grows
    with V/Vrated and with capacitance density (µF per mm³ of case); typical
    published curves: dense X5R/X7R parts lose ~60–80 % near half their rating.
    Reported when the estimate falls below 50 % of nominal."""
    m = _Model(design)
    out = []
    for c in design.chips:
        if not c.ref.startswith("C") or c.dnp:
            continue
        diel = (getattr(c, "dielectric", "") or "").upper()
        if not diel.startswith(("X5", "X7", "X6", "Y5")):
            continue
        cap, vr = getattr(c, "capacitance_f", None), getattr(c, "voltage_rating_v", None)
        vol = _CASE_MM3.get(getattr(c, "package", "") or "")
        nets = _two_nets(c)
        vs = [0.0 if (n and GND_RX.search(n)) else m.volts.get(n) for n in nets]
        if not cap or not vr or not vol or None in vs:
            continue
        v = abs(vs[0] - vs[1])
        dens = cap * 1e6 / vol                          # µF / mm³
        k = 1.6 if dens > 2 else 1.1 if dens > 0.5 else 0.5
        left = max(0.15, 1 - k * v / vr)
        if left < 0.5:
            out.append(("C1", c.ref, f"{c.value} {diel} {c.package} {vr:g} V at {v:g} V: ≈{left*100:.0f} % left "
                                      f"(≈{cap*left*1e6:.2g} µF) on {nets[0]}"))
    return out


def standby_leakage(design, state="aon") -> tuple:
    """L1: resistive standby current in `state` — resistors from an ON rail to
    GND, divider chains rail→node→GND (node with no chip driver), LED chains.
    Returns (total µA, [(µA, description)])."""
    m = _Model(design)
    on = POWER_STATES[state]
    items = []
    seen_nodes = set()
    for c in design.chips:
        if not c.ref.startswith("R") or len(c.pins) != 2 or c.dnp:
            continue
        a, b = _two_nets(c)
        r = _r_ohm(m, c.ref)
        if not r:
            continue
        for x, y in ((a, b), (b, a)):
            if x in on and y and GND_RX.search(y):
                items.append((m.volts[x] / r * 1e6, f"{c.ref} {c.value} {x}→GND"))
            elif x in on and y and not m.is_rail(y) and y not in seen_nodes:
                # divider: y has resistors to GND and no driver
                mem = m.members.get(y, [])
                drivers = [cc for cc, pp in mem if not cc.ref.startswith(("R", "C", "L")) and m.drives(cc, pp)]
                g = [cc for cc, pp in mem if cc.ref.startswith("R") and cc is not c and len(cc.pins) == 2
                     and GND_RX.search(_net(next(q for q in cc.pins if q is not pp)) or "-")]
                if g and not drivers:
                    seen_nodes.add(y)
                    rdn = 1 / sum(1 / _r_ohm(m, cc.ref) for cc in g if _r_ohm(m, cc.ref))
                    items.append((m.volts[x] / (r + rdn) * 1e6, f"{c.ref}+{'+'.join(cc.ref for cc in g)} divider {x}→{y}→GND"))
    items.sort(reverse=True)
    # conditional: pull-ups from an ON rail to a line that something can hold
    # low (a chip output / open-drain / FET drain) — V/R while it is low
    cond = []
    for c in design.chips:
        if not c.ref.startswith("R") or len(c.pins) != 2 or c.dnp:
            continue
        a, b = _two_nets(c)
        r = _r_ohm(m, c.ref)
        for x, y in ((a, b), (b, a)):
            if r and x in on and y and not m.is_rail(y):
                pullers = [f"{cc.ref}.{pp.num}" for cc, pp in m.members.get(y, [])
                           if not cc.ref.startswith(("R", "C", "L", "FB", "TP", "J_CAST"))
                           and (m.ptype(cc, pp) in ("output", "io") or cc.ref.startswith("Q"))]
                if pullers:
                    cond.append((m.volts[x] / r * 1e6, f"{c.ref} {c.value} {x}→{y} while held low by {', '.join(pullers[:3])}"))
    cond.sort(reverse=True)
    return round(sum(i for i, _ in items), 2), items + [(-u, "CONDITIONAL " + t) for u, t in cond]


def temperature(design) -> list:
    """T1: every fitted part's datasheet operating range covers PRODUCT_TEMP_C
    (pinspec _meta.operating_temp_c, else the part's temp_range_c)."""
    out = []
    seen = set()
    for c in design.chips:
        if c.dnp or not c.manf_pn or c.manf_pn in seen:
            continue
        seen.add(c.manf_pn)
        rng = _meta(c.manf_pn).get("operating_temp_c") or getattr(c, "temp_range_c", None)
        if not rng:
            continue
        lo, hi = rng
        if lo > PRODUCT_TEMP_C[0] or hi < PRODUCT_TEMP_C[1]:
            out.append(("T1", c.manf_pn, f"{c.ref}: rated {lo}…{hi} °C, product {PRODUCT_TEMP_C[0]}…{PRODUCT_TEMP_C[1]} °C"))
    return out
