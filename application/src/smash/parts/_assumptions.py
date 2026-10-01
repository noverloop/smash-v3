"""Layered uncertain data: prices, fab country, etc.

Factories should stay focused on hard datasheet facts (pin maps, package
geometry, ratings). Sourcing data — distributor pricing, country of
manufacture, freight notes — drifts on a different cadence: prices move,
suppliers change, and a vendor scrape can't be relied on to track those
changes cleanly. This module keeps that "soft" data in a single
hand-maintained JSON file, joined onto each Chip/Battery via its
`canonical_id` slug at construction time.

Lifecycle:
  - Factory builds a Chip/Battery field dict including `canonical_id="..."`.
  - `Design.add_chip()` / `add_battery()` invokes `apply()` immediately
    after the dataclass is constructed.
  - For every field where the factory passed `None` (i.e. left the slot
    open), the assumption value is written in.
  - Factory-provided values always win over assumptions — a factory can
    promote a number from "assumed" to "ground truth" simply by setting
    it directly, no edit to this file required.

Currently overlaid: price_1pc, currency, price_20kpc, fab_country,
fab_location, weight_g. Anything else listed in an entry is set too,
provided it maps to an existing dataclass field.
"""
from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from smash.parts._slug import canonical_id


_ASSUMPTIONS_OVERLAY_FIELDS: tuple[str, ...] = (
    "price_1pc", "price_20kpc", "currency",
    "fab_country", "fab_location", "weight_g",
)


@cache
def _load() -> dict[str, dict[str, Any]]:
    """Read smash/data/assumptions.json, return {canonical_id: data}.

    Cached for the process lifetime. The file is small enough that a
    single read is fine. If the file is missing or malformed we return
    an empty map and proceed silently — the catalog stays usable even
    without an assumptions layer.
    """
    try:
        text = resources.files("smash.data").joinpath(
            "assumptions.json").read_text()
    except (FileNotFoundError, ModuleNotFoundError):
        return {}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return {}
    # Top-level "_meta" is informational; the parts live under "parts".
    return dict(raw.get("parts", {}))


def apply(obj: Any) -> None:
    """Overlay assumption data onto `obj` (a Chip or Battery instance).

    No-ops when `obj.canonical_id` is None or has no entry. Only
    overwrites fields that are currently None — factory-provided
    values are preserved.
    """
    cid = getattr(obj, "canonical_id", None)
    if not cid:
        # Generic factories (passives, inductors, the QPD detector) often leave
        # canonical_id unset; the assumptions keys ARE manf_pn slugs, so derive
        # it from the part number rather than miss the overlay entirely.
        pn = getattr(obj, "manf_pn", None)
        cid = canonical_id(pn) if pn else None
    if not cid:
        return
    data = _load().get(cid)
    if not data:
        return
    for field in _ASSUMPTIONS_OVERLAY_FIELDS:
        if field not in data:
            continue
        if getattr(obj, field, None) is None:
            setattr(obj, field, data[field])
