"""Bridge: pull thermal specs from `documentation/components.md` and
overlay them onto `Chip` objects.

The parts catalog populates per-chip thermal data (`p_active_w`,
`p_max_w`, `rth_jc_cw`, `tj_max_c`) only sparsely — historically those
numbers lived in a single markdown table in `documentation/
components.md` so they could be reviewed alongside the rest of the BOM
narrative. The bend-sim port doesn't need them; the thermal-sim port
does — and ahead of a full migration of the catalog to carry every
chip's thermal datasheet entry, this module loads the markdown table
and overlays missing fields on `Chip` objects.

CONTRACT: this is a *one-shot bridge*. When the parts catalog absorbs
the thermal table directly (so every chip's factory sets `p_active_w`
etc.), this module becomes a no-op and can be removed.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re


from smash.roots import git_repo_root

_COMPONENTS_MD = git_repo_root() / "documentation" / "components.md"
_SECTION_HEADING = "## Thermal characteristics"

# Same regex as the legacy thermal_sim/components.py — one row
# of the markdown table:
#   | **NAME** (...optional aside) | Pkg | P_active | P_max | Rjc | Rja | Tjmax | Source |
_ROW_RE = re.compile(
    r"^\|\s*\*\*([^*]+)\*\*\s*([^|]*)\|"   # bolded name + optional aside
    r"([^|]*)\|"                            # package
    r"([^|]*)\|"                            # P_active
    r"([^|]*)\|"                            # P_max
    r"([^|]*)\|"                            # Rth_jc
    r"([^|]*)\|"                            # Rth_ja
    r"([^|]*)\|"                            # T_jmax
    r"([^|]*)\|\s*$"                        # source
)


@dataclasses.dataclass
class ThermalSpec:
    name: str
    package: str
    p_active_w: float
    p_max_w: float
    rth_jc_cw: float | None
    rth_ja_cw: float | None
    tj_max_c: float | None
    estimated: bool
    source: str


def _parse_float(cell: str) -> tuple[float | None, bool]:
    text = cell.strip().replace("—", "").replace("`", "")
    estimated = "*" in text
    if not text:
        return None, estimated
    m = re.search(r"<?\s*(\d+(?:\.\d+)?)\s*", text)
    if not m:
        return None, estimated
    return float(m.group(1)), estimated


def _split_aliases(bolded: str) -> list[str]:
    """`'LDL112PV33R / PV18R'` → `['LDL112PV33R', 'LDL112PV18R']` etc."""
    parts = [p.strip() for p in bolded.split("/")]
    if len(parts) <= 1:
        return [bolded.strip()]
    base = parts[0]
    aliases = [base]
    for variant in parts[1:]:
        if len(variant) >= 6 and any(c.isdigit() for c in variant):
            # Borrow common prefix from the previous full name.
            for cut in range(len(base) - 1, 0, -1):
                aliases.append(base[:cut] + variant)
                break
        else:
            aliases.append(variant)
    return aliases


def load_thermal_specs(components_md: pathlib.Path = _COMPONENTS_MD,
                       ) -> dict[str, ThermalSpec]:
    """Return `{part_number: ThermalSpec}` parsed from the markdown
    table in `documentation/components.md`."""
    text = pathlib.Path(components_md).read_text()
    start = text.find(_SECTION_HEADING)
    if start < 0:
        raise FileNotFoundError(
            f"'{_SECTION_HEADING}' not found in {components_md}")
    end = text.find("\n---\n", start)
    section = text[start:end] if end > 0 else text[start:]

    specs: dict[str, ThermalSpec] = {}
    for line in section.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        name_raw, _aside, pkg, p_a, p_m, rjc, rja, tjmax, src = m.groups()
        if name_raw.strip().lower().startswith("all "):
            continue
        p_active, ea = _parse_float(p_a)
        p_max, eb = _parse_float(p_m)
        rth_jc, ec = _parse_float(rjc)
        rth_ja, ed = _parse_float(rja)
        t_jmax, ee = _parse_float(tjmax)
        if p_active is None and p_max is None:
            continue
        spec = ThermalSpec(
            name=name_raw.strip(), package=pkg.strip(),
            p_active_w=p_active or 0.0,
            p_max_w=p_max or p_active or 0.0,
            rth_jc_cw=rth_jc, rth_ja_cw=rth_ja, tj_max_c=t_jmax,
            estimated=any((ea, eb, ec, ed, ee)),
            source=src.strip(),
        )
        for alias in _split_aliases(name_raw.strip()):
            specs[alias] = spec
    return specs


def _match(specs: dict, manf_pn: str | None) -> ThermalSpec | None:
    """Find a spec for a given `manf_pn`. Falls back to prefix match
    (so `TCAN1042GVDQ1` finds the `TCAN1042GVD` row)."""
    if not manf_pn:
        return None
    if manf_pn in specs:
        return specs[manf_pn]
    for key, sp in specs.items():
        if manf_pn.startswith(key) or key.startswith(manf_pn[:8]):
            return sp
    return None


def overlay_chip_thermals(design, specs: dict | None = None) -> int:
    """Walk every chip in `design.chips` (or `design.chips_in_order()`)
    and fill in `p_active_w` / `p_max_w` / `rth_jc_cw` / `tj_max_c`
    from the markdown spec table where the chip doesn't already carry
    them. Returns the number of chips that received any overlay.

    The catalog wins — pre-populated thermal fields are NOT overwritten.
    """
    if specs is None:
        specs = load_thermal_specs()
    n = 0
    chips = (design.chips.values() if isinstance(design.chips, dict)
             else design.chips)
    for chip in chips:
        sp = _match(specs, getattr(chip, "manf_pn", None))
        if sp is None:
            continue
        touched = False
        for field, val in (("p_active_w", sp.p_active_w),
                           ("p_max_w",    sp.p_max_w),
                           ("rth_jc_cw",  sp.rth_jc_cw),
                           ("tj_max_c",   sp.tj_max_c)):
            if getattr(chip, field, None) is None and val is not None \
                    and val > 0:
                setattr(chip, field, val)
                touched = True
        if touched:
            n += 1
    return n
