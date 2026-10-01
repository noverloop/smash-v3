"""Value-string parsers for passive factories.

Catalog factories accept human-readable value strings ("100nF", "10k",
"4.7uH") and store the numeric SI value on the Chip dataclass
(capacitance_f, resistance_ohm, inductance_h). These helpers do the
parsing without inventing units or values that aren't in the source.
"""

from __future__ import annotations

import re


_SI_PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6,
    "m": 1e-3, "":  1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}


def parse_capacitance_f(value: str) -> float:
    """`"100nF"` → 1e-7, `"4.7uF"` → 4.7e-6, `"22uF/16V"` → 22e-6
    (voltage-rating suffix after '/' dropped). Raises ValueError on
    unparseable input."""
    s = value.strip().split("/", 1)[0].lower().replace(" ", "")
    m = re.fullmatch(r"([\d.]+)\s*([pnumµk]?)f?", s)
    if not m:
        raise ValueError(f"unparseable capacitance value: {value!r}")
    num = float(m.group(1))
    prefix = m.group(2)
    if prefix not in _SI_PREFIX:
        raise ValueError(f"unknown SI prefix {prefix!r} in {value!r}")
    return num * _SI_PREFIX[prefix]


def parse_resistance_ohm(value: str) -> float:
    """`"4.7k"` → 4700, `"100"` → 100, `"49k9"` → 49900 (R-notation),
    `"0.1"` → 0.1, `"100m"` → 0.1 (milli), `"1.5M"` → 1.5e6 (mega).

    Case matters for `m` vs `M`: lowercase = milli (10⁻³), uppercase
    = mega (10⁶). `r/R` are interchangeable (decimal-substitute
    notation common in resistor markings: `4R7` = 4.7 Ω, `49k9` = 49.9 kΩ).
    """
    s = value.strip().replace(" ", "")
    # R/k/M-notation as decimal substitute: "4R7" = 4.7, "49k9" = 49.9k
    m = re.fullmatch(r"(\d+)([rRkKmM])(\d+)", s)
    if m:
        whole, prefix, frac = m.group(1), m.group(2), m.group(3)
        num = float(f"{whole}.{frac}")
        if prefix in ("r", "R"):
            return num
        return num * _SI_PREFIX[prefix]
    # Plain "100" / "4.7k" / "100m" / "1.5M" / "0R" form
    m = re.fullmatch(r"([\d.]+)\s*([rRkKmMµu]?)", s)
    if not m:
        raise ValueError(f"unparseable resistance value: {value!r}")
    num = float(m.group(1))
    prefix = m.group(2)
    if prefix in ("r", "R", ""):
        return num
    if prefix not in _SI_PREFIX:
        raise ValueError(f"unknown SI prefix {prefix!r} in {value!r}")
    return num * _SI_PREFIX[prefix]


def parse_inductance_h(value: str) -> float:
    """`"4.7uH"` → 4.7e-6, `"10uH"` → 1e-5, `"100nH"` → 1e-7,
    `"4u7"` → 4.7e-6 (engineering R-notation also accepted with `u`
    as the decimal). Raises ValueError on unparseable input."""
    s = value.strip().lower().replace(" ", "")
    # u-notation: "4u7" = 4.7 µH
    m = re.fullmatch(r"(\d+)u(\d+)h?", s)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}") * 1e-6
    m = re.fullmatch(r"(\d+)n(\d+)h?", s)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}") * 1e-9
    # Plain "4.7uH" form
    m = re.fullmatch(r"([\d.]+)\s*([pnumµ]?)h?", s)
    if not m:
        raise ValueError(f"unparseable inductance value: {value!r}")
    num = float(m.group(1))
    prefix = m.group(2)
    if prefix not in _SI_PREFIX:
        raise ValueError(f"unknown SI prefix {prefix!r} in {value!r}")
    return num * _SI_PREFIX[prefix]
