"""CSV BOM writer.

Ports `_write_bom` from system.py into a Design-consuming library
function. Per-board grouping, optional DNP/ECM marking for parts
absorbed by an embedded-capacitance laminate, totals row at the bottom.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping

from smash.state import Design
from smash.export._common import all_components, footprint_full


_FIELDS = [
    "Board", "Ref", "Value", "Footprint", "Description",
    "Manf", "Manf_PN", "Fab_Country", "Cost_USD",
]


def write_bom(
    design: Design,
    path: str | Path,
    *,
    dnp_refs: set[str] | None = None,
    fx_rates: Mapping[str, float] | None = None,
) -> dict:
    """Write a CSV BOM for `design` to `path`.

    Args:
      design:  the Design to render.
      path:    output filename (will be overwritten).
      dnp_refs: optional set of part refs to mark as
                "[DNP/ECM]" with cost zeroed — used by the
                embedded-cap-laminate build mode where per-IC HF
                decoupling caps are absorbed by the laminate plane.
                Caller decides which refs qualify (typically the set
                where build flag `embedded_cap_absorbs=True` was set
                during construction).
      fx_rates: optional ISO-4217 → USD multiplier map. Used to
                convert non-USD prices to USD. If a component's
                currency isn't in the map (and isn't USD), its
                cost stays blank.

    Returns a small summary dict: {n_parts, total_usd, n_dnp,
    dnp_saved_usd}. Output CSV has one row per component sorted by
    (board, ref), plus trailing totals + DNP-saved lines.
    """
    # When dnp_refs isn't explicitly given, auto-derive from Chip.dnp on the
    # Design — that's where build helpers (cap_to_gnd / res_between / ...)
    # mark ECM-absorbed or otherwise unpopulated parts.
    if dnp_refs is None:
        dnp_refs = {
            c.ref for c in (list(design.chips) + list(design.batteries) + list(getattr(design, "antennas", [])))
            if getattr(c, "dnp", False)
        }
    else:
        dnp_refs = set(dnp_refs)
    fx_rates = dict(fx_rates or {})
    fx_rates.setdefault("USD", 1.0)

    rows: list[dict] = []
    total = 0.0
    dnp_count = 0
    dnp_saved = 0.0

    for c in all_components(design):
        ref = c.ref
        board = getattr(c, "board_tag", "") or ""
        cost_usd = _component_cost_usd(c, fx_rates)
        desc = getattr(c, "description", "") or ""
        is_dnp = ref in dnp_refs
        if is_dnp:
            dnp_count += 1
            if cost_usd is not None:
                dnp_saved += cost_usd
            desc = "[DNP/ECM] " + desc
            cost_usd = 0.0
        if cost_usd is not None:
            total += cost_usd
        rows.append({
            "Board":       board,
            "Ref":         ref,
            "Value":       getattr(c, "value", "") or "",
            "Footprint":   footprint_full(c),
            "Description": desc,
            "Manf":        getattr(c, "manf", "") or "",
            "Manf_PN":     getattr(c, "manf_pn", "") or "",
            "Fab_Country": getattr(c, "fab_country", "") or "",
            "Cost_USD":    f"{cost_usd:.2f}" if cost_usd is not None else "",
        })

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        w.writerows(rows)
        f.write(f"\nTOTAL BOM COST (one unit),,,,,,,, ${total:.2f}\n")
        if dnp_count:
            f.write(
                f"DNP (absorbed by ECM layer),,,,,,,, "
                f"{dnp_count} parts / ${dnp_saved:.2f} saved\n"
            )
    return {
        "n_parts":       len(rows),
        "total_usd":     total,
        "n_dnp":         dnp_count,
        "dnp_saved_usd": dnp_saved,
    }


def _component_cost_usd(c, fx_rates: Mapping[str, float]) -> float | None:
    """Convert a component's listed price_1pc to USD via fx_rates."""
    price = getattr(c, "price_1pc", None)
    if price is None:
        return None
    currency = getattr(c, "currency", None) or "USD"
    rate = fx_rates.get(currency)
    if rate is None:
        return None
    return float(price) * float(rate)
