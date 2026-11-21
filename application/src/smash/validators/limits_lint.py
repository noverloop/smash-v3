"""Lint the per-part ``limits.json`` files (2026-11-21).

Checks each file parses, follows electrical.LIMITS_SCHEMA, cites a datasheet
reference on every entry, and that every pin it names exists on the part's
symbol in the design (by number, name or alias). Run:

    python -m smash.validators.limits_lint            # all files
"""
from __future__ import annotations

import json
import sys

from smash.validators.electrical import _sources_dir, _pins_of


def lint(d) -> list:
    chips = {}
    for c in d.chips:
        chips.setdefault(str(c.manf_pn or "").upper(), c)
    problems = []
    for f in sorted(_sources_dir().glob("*/limits.json")):
        where = f.parent.name
        try:
            j = json.loads(f.read_text())
        except Exception as e:
            problems.append(f"{where}: not valid JSON ({e})")
            continue
        part = str(j.get("part", "")).upper()
        c = chips.get(part)
        if c is None:
            problems.append(f"{where}: part {j.get('part')!r} not in the design")
            continue
        for key in ("supplies", "io", "open_drain", "required"):
            for k, e in enumerate(j.get(key, []) or []):
                if not e.get("ref"):
                    problems.append(f"{where}: {key}[{k}] has no datasheet ref")
                pins = e.get("pins")
                if pins and pins != ["*"]:
                    found = _pins_of(c, pins)
                    names = {str(p.num).upper() for p in found} | {str(p.name or "").upper() for p in found}
                    missing = [p for p in pins if str(p).upper() not in names
                               and not any(str(p).upper() in [str(a).upper() for a in (q.aliases or [])] for q in found)]
                    if missing:
                        problems.append(f"{where}: {key}[{k}] pins not on the symbol: {missing}")
        for k, s in enumerate(j.get("supplies", []) or []):
            lo, hi, am = s.get("min_v"), s.get("max_v"), s.get("abs_max_v")
            if lo is not None and hi is not None and lo > hi:
                problems.append(f"{where}: supplies[{k}] min {lo} > max {hi}")
            if hi is not None and am is not None and am < hi:
                problems.append(f"{where}: supplies[{k}] abs max {am} < max {hi}")
        for k, g in enumerate(j.get("io", []) or []):
            if g.get("abs_max_v") is None and g.get("abs_max_over_domain_v") is None:
                problems.append(f"{where}: io[{k}] has neither abs_max_v nor abs_max_over_domain_v")
            dom = g.get("domain")
            if dom and g.get("abs_max_v") is None:
                sup = [p for s in j.get("supplies", []) for p in (s.get("pins") or [])]
                if not _pins_of(c, [dom]) and dom not in sup:
                    problems.append(f"{where}: io[{k}] domain {dom!r} is not a supply pin")
        if j.get("i2c"):
            bp = (j["i2c"].get("bus_pins") or {})
            for role in ("SCL", "SDA"):
                if bp.get(role) and not _pins_of(c, [bp[role]]):
                    problems.append(f"{where}: i2c {role} pin {bp[role]!r} not on the symbol")
    return problems


if __name__ == "__main__":
    import pathlib
    repo = pathlib.Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(repo))
    import generate_stackup as G
    import generate_devboard as GD
    d = G.Design(); G._set_battery_mode("maximalist"); G._prime_power_rails(d)
    for fn in GD._BUILDERS:
        fn(d)
    p = lint(d)
    print("\n".join(p) if p else "limits.json: all clean")
    sys.exit(1 if p else 0)
