"""Best-known component height, for spacer-gap clearance.

A spacer between two rigid tiles must clear, at every (x,y), the sum of the
lower tile's top-face chip height and the upper tile's bottom-face chip height
(opposing parts share the gap — a tall part over a tall part collides unless
the spacer is at least their combined height). To size or audit that, we need
each footprint's height. Resolution order, most → least trustworthy:

  1. `footprint.height_mm` — the datasheet value.
  2. the height field ENCODED IN THE IPC-7351 footprint name — e.g.
     `SON127P800X600X65-8N` → the trailing `X65-8N` ⇒ 0.65 mm. This is the
     part's actual spec'd height (SamacSys bakes the datasheet dimension into
     the name), NOT a package-family guess.
  3. a worst-case assumption (default 2.0 mm) when neither is available.

NOTE — the STEP 3D model is deliberately NOT in this chain. bbox-Z looks like
the obvious height source but it's unreliable: KiCad 3D models aren't
consistently oriented, so a part lying on its side reports its body length as
"height" (e.g. the MT29F SPI-NAND's model gives bbox-Z = 6.0 mm vs. its true
0.65 mm). `step_height_mm()` is kept for manual cross-checking only.
"""
from __future__ import annotations

import pathlib
import re

# IPC-7351 / SamacSys names end `…X<H>-<pins><thermal>`, H in 0.01 mm
# (the last X-field before the pin count is the body height). Two-terminal
# names carry no pin-count field at all — `DIOM7958X256N`, `INDPM4848X280N`
# — and some carry a trailing variant letter after it (`…X90-57N-D`), so
# both the `-<pins>` group and a `-<letters>` tail are optional. Without
# that a 2.56 mm diode silently resolved to the 2.0 mm worst-case
# assumption and under-sized the spacer gap it sat in.
_IPC_HEIGHT_RE = re.compile(r"X(\d+)(?:-\d+)?[A-Za-z]*(?:-[A-Za-z]+)?$")

_step_height_cache: dict[str, float | None] = {}


def ipc_name_height_mm(name: str | None) -> float | None:
    """Height (mm) encoded in an IPC-7351 footprint name, or None.

    `SON127P800X600X65-8N` → 0.65; `SOP65P640X120-17N` → 1.20. Sanity-bounded
    to (0, 30) mm so a stray match can't inject a garbage height."""
    if not name:
        return None
    m = _IPC_HEIGHT_RE.search(name)
    if not m:
        return None
    h = int(m.group(1)) / 100.0
    # Plausibility floor: names that merely LOOK like IPC-7351 can match by
    # accident — the IR emitter's part-number footprint `VSMB1940X01` parses
    # as 0.01 mm. No real package is thinner than ~0.2 mm, so anything under
    # 0.1 mm is a mis-parse and must fall through to the assumption rather
    # than under-size a spacer gap.
    return h if 0.1 <= h < 30.0 else None


def step_height_mm(step_path: str | pathlib.Path) -> float | None:
    """Z-extent (mm) of a STEP file's solid bounding box. CAUTION: this is the
    model's Z span, which is the part height ONLY if the model is upright —
    many KiCad models are rotated, so this is for manual cross-checking, not
    automated height resolution. Returns None on failure; cached by path."""
    key = str(step_path)
    if key in _step_height_cache:
        return _step_height_cache[key]
    h: float | None
    try:
        import cadquery as cq
        shp = cq.importers.importStep(key)
        h = float(shp.val().BoundingBox().zlen)
    except Exception:
        h = None
    _step_height_cache[key] = h
    return h


def footprint_height_mm(
    footprint,
    *,
    assume_mm: float = 2.0,
) -> tuple[float, str]:
    """Best-known height (mm) for `footprint` + its source tag.

    Returns ``(height_mm, source)`` where source is "datasheet", "name", or
    "assumed". `assume_mm` is the worst-case fallback when there is neither a
    datasheet height nor a name-encoded one.
    """
    if footprint is None:
        return assume_mm, "assumed"
    h = getattr(footprint, "height_mm", None)
    if h:
        return float(h), "datasheet"
    nh = ipc_name_height_mm(getattr(footprint, "name", None))
    if nh is not None:
        return nh, "name"
    return assume_mm, "assumed"
