"""Electrical rules check (2026-11-21, user): what ERC can't see.

ERC only checks pin TYPES (is an input driven, do two outputs fight). This
checks the electrical facts the design data + the datasheets can answer, and
reports WARNINGS (never a build gate):

  E1  single-pin nets            a signal that goes nowhere (the 2026-11-21
                                 camera I2C / reset bug, RF_SW_CTRL)
  E2  I2C pull-ups               every SCL / SDA net has a pull-up to a rail
  E3  capacitor voltage rating   rating ≥ DERATE × the voltage across it
  E4  supply pins in range       a datasheet supply pin sits on a rail inside
                                 its recommended operating range
  E5  I/O pins within abs max    an I/O pin's net never exceeds its domain's
                                 absolute maximum (e.g. 3.3 V into a 1.8 V pin)
  E6  open-drain pull-ups        a datasheet open-drain output has a pull-up
  E7  I2C address map            no two devices answer the same address on
                                 one bus

E1–E3 need only the design. E4–E7 read a per-part ``limits.json`` next to the
part's datasheet in ``smash/parts/sources/<PN>/`` (schema: LIMITS_SCHEMA
below). Every value there carries the datasheet page/table it came from, so
a flagged result can be checked against the PDF; a part without the file is
simply not checked for E4–E7 (listed as uncovered).

Rail voltages: the nets that already carry ``voltage_v`` (every power rail)
are propagated through 0 Ω links and ferrite beads to every net they reach.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import re

DERATE = 1.25            # ceramic caps: DC-bias + margin (rating ≥ 1.25 × V)
RAIL_TOL = 0.05          # nominal rails taken as ±5 % for range checks

LIMITS_SCHEMA = """\
{
  "part": "<manf_pn as in the datasheet>",
  "datasheet": "<pdf file name in this folder>",
  "extracted": "<date> by <who> — values cite the datasheet; spot-check before trusting",
  "supplies": [            # E4: one entry per supply group
    {"pins": ["<pin name or number>", ...], "min_v": 1.7, "max_v": 1.9,
     "abs_max_v": 2.1, "ref": "p.12 Table 5"}
  ],
  "io": [                  # E5: I/O groups and the supply that clamps them
    {"pins": ["<names>" | "*"], "domain": "<supply pin name, e.g. VDD_IO>",
     "abs_max_over_domain_v": 0.3, "abs_max_v": null, "ref": "p.10 Table 3"}
  ],
  "open_drain": [{"pins": ["SDA", "INT"], "ref": "p.20"}],          # E6
  "i2c": {"bus_pins": {"SCL": "<pin>", "SDA": "<pin>"},            # E7
          "address": {"default": "0x10",
                      "strap": {"pin": "SADDR", "GND": "0x10", "VDD": "0x18"}},
          "ref": "p.30"},
  "required": [{"what": "100 nF per VDD ball", "ref": "p.40"}]     # informational
}"""


@dataclasses.dataclass
class Finding:
    rule: str
    where: str
    msg: str

    def __str__(self) -> str:
        return f"{self.rule} {self.where}: {self.msg}"


# ── net model ────────────────────────────────────────────────────────────

def _pin_net(d) -> dict:
    """{(ref, pin_num): net_name} from the design's nets."""
    out = {}
    for n in d.nets:
        for p in getattr(n, "pins", None) or []:
            ref, num = (p if isinstance(p, tuple) else (getattr(p, "chip_ref", None),
                                                       getattr(p, "num", None)))
            out[(ref, str(num))] = n.name
    return out


def _net_members(d) -> dict:
    out = {}
    for n in d.nets:
        mem = []
        for p in getattr(n, "pins", None) or []:
            ref, num = (p if isinstance(p, tuple) else (getattr(p, "chip_ref", None),
                                                       getattr(p, "num", None)))
            mem.append((ref, str(num)))
        out[n.name] = mem
    return out


def _is_zero_ohm(c) -> bool:
    v = str(getattr(c, "value", "") or "").replace(" ", "").upper()
    return c.ref.startswith("R") and v in ("0", "0R", "0Ω", "0OHM", "0E")


def _is_bead(c) -> bool:
    pn = str(getattr(c, "manf_pn", "") or "").upper()
    return c.ref.startswith(("FB", "L_FB")) or pn.startswith(("BLM", "MPZ", "BK"))


def net_voltages(d) -> dict:
    """{net: volts}: the rails' voltage_v, propagated through 0 Ω / beads.
    Ground nets are 0 V."""
    v = {n.name: float(n.voltage_v) for n in d.nets if getattr(n, "voltage_v", None) is not None}
    for n in d.nets:
        if getattr(n, "kind", None) == "ground" or n.name in ("GND", "FLEX_GND"):
            v[n.name] = 0.0
    pn = _pin_net(d)
    links = []
    for c in d.chips:
        if len(c.pins) == 2 and (_is_zero_ohm(c) or _is_bead(c)):
            a, b = (pn.get((c.ref, str(p.num))) for p in c.pins)
            if a and b:
                links.append((a, b))
    changed = True
    while changed:
        changed = False
        for a, b in links:
            if a in v and b not in v:
                v[b] = v[a]; changed = True
            elif b in v and a not in v:
                v[a] = v[b]; changed = True
    return v


# ── limits files ─────────────────────────────────────────────────────────

def _sources_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1] / "parts" / "sources"


def load_limits(pn: str) -> dict | None:
    """The limits.json of a part number (folder name = PN, or a folder whose
    limits.json names it)."""
    root = _sources_dir()
    cand = [root / re.sub(r"[/#]", "_", pn) / "limits.json"]
    cand += [p / "limits.json" for p in root.glob(f"{re.sub(r'[^A-Za-z0-9]', '?', pn)}*")]
    for f in cand:
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                return None
    for f in root.glob("*/limits.json"):
        try:
            j = json.loads(f.read_text())
        except Exception:
            continue
        if str(j.get("part", "")).upper() == pn.upper():
            return j
    return None


def _pins_of(chip, sel) -> list:
    """Chip pins matching a list of names / numbers ('*' = every io pin)."""
    if sel == ["*"] or sel == "*":
        return [p for p in chip.pins if (p.type or "io") in ("io", "input", "output", "clock")]
    want = {str(s).upper() for s in sel}
    return [p for p in chip.pins
            if str(p.num).upper() in want or str(p.name or "").upper() in want
            or any(str(a).upper() in want for a in (p.aliases or []))]


# ── the rules ────────────────────────────────────────────────────────────

_SKIP_SINGLE = re.compile(r"^(TWR_|TP_|unconnected|NC_|N\$)|_NC$|NC\d*$")


def check(d) -> dict:
    """Run E1–E7. Returns {"findings": [Finding], "uncovered": [pn], ...}."""
    pn_of = {c.ref: c for c in d.chips}
    pin_net = _pin_net(d)
    members = _net_members(d)
    V = net_voltages(d)
    out: list[Finding] = []

    # E1 single-pin nets
    for net, mem in members.items():
        if len(mem) == 1 and not _SKIP_SINGLE.search(net):
            ref, num = mem[0]
            c = pn_of.get(ref)
            p = next((q for q in (c.pins if c else []) if str(q.num) == num), None)
            if p is not None and (p.type or "") in ("nc", "reserved"):
                continue
            out.append(Finding("E1", net, f"only {ref} pin {num} — goes nowhere"))

    # E2 I2C pull-ups (to a net with a known voltage)
    def pullups(net):
        res = []
        for ref, num in members.get(net, []):
            c = pn_of.get(ref)
            if c is None or not ref.startswith("R") or len(c.pins) != 2:
                continue
            other = [pin_net.get((ref, str(p.num))) for p in c.pins if str(p.num) != num]
            if other and other[0] in V and V[other[0]] > 0.5:
                res.append((ref, other[0]))
        return res
    for net in members:
        if re.search(r"(^|_)(SCL|SDA)(_|$)", net) and len(members[net]) > 1:
            if not pullups(net):
                out.append(Finding("E2", net, "I2C line has no pull-up to a rail"))

    # E3 capacitor rating
    for c in d.chips:
        r = getattr(c, "voltage_rating_v", None)
        if not c.ref.startswith("C") or r is None or len(c.pins) != 2:
            continue
        a, b = (pin_net.get((c.ref, str(p.num))) for p in c.pins)
        if a in V and b in V:
            across = abs(V[a] - V[b])
            if across > 0 and r < DERATE * across:
                out.append(Finding("E3", c.ref, f"rated {r:g} V across {across:g} V "
                                   f"({a}–{b}); want ≥ {DERATE:g}×"))

    # E4–E7 from the datasheet limits
    uncovered, covered = [], []
    i2c_map: dict = {}
    for c in d.chips:
        if getattr(c, "manf", None) == "project" or not c.manf_pn:
            continue
        if c.ref.startswith(("R", "C", "L", "FB")) and len(c.pins) == 2:
            continue                                  # passives: E3 only
        lim = load_limits(c.manf_pn)
        if lim is None:
            uncovered.append(c.manf_pn)
            continue
        covered.append(c.manf_pn)
        ref_of = lambda e: f" [{e.get('ref', '?')}]"
        dom_v = {}
        for s in lim.get("supplies", []):                              # E4
            for p in _pins_of(c, s.get("pins", [])):
                net = pin_net.get((c.ref, str(p.num)))
                dom_v[str(p.name or p.num).upper()] = V.get(net)
                if net is None or net not in V:
                    continue
                v = V[net]
                lo, hi = s.get("min_v"), s.get("max_v")
                if (lo is not None and v * (1 + RAIL_TOL) < lo) or (hi is not None and v * (1 - RAIL_TOL) > hi):
                    out.append(Finding("E4", f"{c.ref}.{p.name or p.num}",
                                       f"on {net} = {v:g} V, datasheet {lo}–{hi} V{ref_of(s)}"))
        for g in lim.get("io", []):                                     # E5
            dv = dom_v.get(str(g.get("domain", "")).upper())
            amax = g.get("abs_max_v")
            if amax is None and dv is not None and g.get("abs_max_over_domain_v") is not None:
                amax = dv + g["abs_max_over_domain_v"]
            if amax is None:
                continue
            for p in _pins_of(c, g.get("pins", ["*"])):
                net = pin_net.get((c.ref, str(p.num)))
                if net in V and V[net] > amax:
                    out.append(Finding("E5", f"{c.ref}.{p.name or p.num}",
                                       f"on {net} = {V[net]:g} V > abs max {amax:g} V{ref_of(g)}"))
        for g in lim.get("open_drain", []):                             # E6
            for p in _pins_of(c, g.get("pins", [])):
                net = pin_net.get((c.ref, str(p.num)))
                if net and len(members.get(net, [])) > 1 and not pullups(net):
                    out.append(Finding("E6", f"{c.ref}.{p.name or p.num}",
                                       f"open-drain on {net} has no pull-up{ref_of(g)}"))
        i2c = lim.get("i2c")                                            # E7
        if i2c:
            scl_pin = (i2c.get("bus_pins") or {}).get("SCL")
            bus = next((pin_net.get((c.ref, str(p.num))) for p in _pins_of(c, [scl_pin])), None) if scl_pin else None
            addr = (i2c.get("address") or {}).get("default")
            strap = (i2c.get("address") or {}).get("strap")
            if strap:
                sp = next(iter(_pins_of(c, [strap.get("pin")])), None)
                snet = pin_net.get((c.ref, str(sp.num))) if sp else None
                if snet in V:
                    addr = strap.get("GND") if V[snet] < 0.5 else strap.get("VDD", addr)
            if bus and addr:
                i2c_map.setdefault(bus, []).append((addr.lower(), c.ref))
    for bus, devs in i2c_map.items():
        seen = {}
        for a, ref in devs:
            if a in seen:
                out.append(Finding("E7", bus, f"{seen[a]} and {ref} both answer {a}"))
            seen.setdefault(a, ref)
    return {"findings": out, "covered": sorted(set(covered)),
            "uncovered": sorted(set(uncovered)), "voltages": V, "i2c": i2c_map}


def acknowledged() -> dict:
    f = pathlib.Path(__file__).with_name("erc_acknowledged.json")
    try:
        return {k: v for k, v in json.loads(f.read_text()).items() if not k.startswith("_")}
    except Exception:
        return {}


def report(d, label: str = "design") -> dict:
    """Print the findings as WARN lines (grouped by rule); reviewed ones
    (erc_acknowledged.json) are only counted."""
    r = check(d)
    ack = acknowledged()
    live = [f for f in r["findings"] if f"{f.rule} {f.where}" not in ack]
    r["acknowledged"] = len(r["findings"]) - len(live)
    by = {}
    for f in live:
        by.setdefault(f.rule, []).append(f)
    print(f"Electrical rules check — {label} (warnings only — not a build gate):")
    if not live:
        print("  clean" + (f" ({r['acknowledged']} reviewed finding(s) acknowledged)" if r["acknowledged"] else ""))
    elif r["acknowledged"]:
        print(f"  ({r['acknowledged']} reviewed finding(s) acknowledged — erc_acknowledged.json)")
    for rule in sorted(by):
        for f in by[rule]:
            print(f"  WARN {f}")
    print(f"  datasheet limits: {len(r['covered'])} part numbers covered, "
          f"{len(r['uncovered'])} not yet ({', '.join(r['uncovered'][:8])}"
          f"{', …' if len(r['uncovered']) > 8 else ''})")
    return r
