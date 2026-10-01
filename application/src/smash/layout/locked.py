"""Locked-placement loader — reads `smash/data/locked_placements.json`.

Each entry pins one ref's `Placement` (board-local position + rotation
+ optional face). The placer reads this file before the radial packer
runs; locked refs are skipped by the packer and emitted as
`Placement(..., locked=True)` at the recorded coords.

Future scope: locked trace segments. Smash doesn't model traces yet,
so this loader only handles chip placements today.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class LockedPlacement:
    """One pinned placement entry from `locked_placements.json`."""
    position_mm: tuple[float, float]
    rotation_deg: float = 0.0
    face: str = "top"             # "top" | "bottom"
    reason: str | None = None     # human-readable rationale


@cache
def load_locked_placements() -> dict[str, LockedPlacement]:
    """Return `{ref: LockedPlacement}`.

    Cached for the process lifetime. Reads the JSON, skips the `_meta`
    block, validates each entry's shape. Missing file → empty dict
    (placer runs with no anchors). Malformed JSON or per-entry schema
    errors raise — locked placements are load-bearing, silent failure
    here would let the placer move the MPU/DDR3.
    """
    try:
        text = resources.files("smash.data").joinpath(
            "locked_placements.json").read_text()
    except (FileNotFoundError, ModuleNotFoundError):
        return {}

    raw = json.loads(text)  # raises on malformed JSON — intentional
    out: dict[str, LockedPlacement] = {}
    for ref, entry in raw.items():
        if ref.startswith("_"):     # skip _meta and similar
            continue
        out[ref] = _parse_entry(ref, entry)
    return out


def _parse_entry(ref: str, entry: dict[str, Any]) -> LockedPlacement:
    if not isinstance(entry, dict):
        raise ValueError(
            f"locked_placements.json: entry for {ref!r} must be an "
            f"object, got {type(entry).__name__}"
        )
    pos = entry.get("position_mm")
    if not (isinstance(pos, (list, tuple)) and len(pos) == 2
            and all(isinstance(v, (int, float)) for v in pos)):
        raise ValueError(
            f"locked_placements.json[{ref}]: position_mm must be "
            f"[x, y] floats, got {pos!r}"
        )
    rot = entry.get("rotation_deg", 0)
    if not isinstance(rot, (int, float)):
        raise ValueError(
            f"locked_placements.json[{ref}]: rotation_deg must be "
            f"a number, got {rot!r}"
        )
    face = entry.get("face", "top")
    if face not in ("top", "bottom"):
        raise ValueError(
            f"locked_placements.json[{ref}]: face must be 'top' or "
            f"'bottom', got {face!r}"
        )
    return LockedPlacement(
        position_mm=(float(pos[0]), float(pos[1])),
        rotation_deg=float(rot),
        face=face,
        reason=entry.get("reason"),
    )
