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
  3. (2026-11-20, user) the TOP of the vendor STEP model AFTER the
     footprint's KiCad model transform (rotation + offset, as KiCad's STEP
     export applies it). The raw bbox-Z was unreliable — models lie on their
     side (the MT29F SPI-NAND read 6.0 mm vs 0.65) — but with the transform
     applied 38/48 models match the datasheet within 15 % and the rest within
     0.3 mm (nominal vs max), the NAND included. Cached on disk.
  4. a worst-case assumption (default 2.0 mm) when none is available.
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


def _model_cache_path():
    return pathlib.Path(__file__).resolve().parents[4] / ".cache" / "model_heights.json"


def model_top_mm(footprint) -> float | None:
    """Top (mm above the board) of `footprint`'s STEP model after its KiCad
    model transform; None without a usable model. Disk-cached per file."""
    mp = getattr(footprint, "model_3d_path", None)
    if not mp or mp.startswith("${"):
        return None
    import json
    from smash.export.kicad_pcb import _parse_kicad_mod_model_xform, resolve_repo_path
    path = resolve_repo_path(mp)
    if not path.exists():
        return None
    off, rot = getattr(footprint, "model_offset_mm", None), getattr(footprint, "model_rotate_deg", None)
    if off is None and rot is None:
        off, rot = next((x for x in (_parse_kicad_mod_model_xform(m)
                                     for m in sorted(path.parent.glob("*.kicad_mod"))) if x),
                        ((0, 0, 0), (0, 0, 0)))
    off, rot = tuple(off or (0, 0, 0)), tuple(rot or (0, 0, 0))
    st = path.stat()
    key = f"{path}|{st.st_size}|{int(st.st_mtime)}|{off}|{rot}"
    if key in _step_height_cache:
        return _step_height_cache[key]
    cp = _model_cache_path()
    disk = {}
    try:
        disk = json.loads(cp.read_text())
    except Exception:
        pass
    if key in disk:
        _step_height_cache[key] = disk[key]
        return disk[key]
    try:
        import cadquery as cq
        sh = cq.importers.importStep(str(path)).val()
        sh = (sh.rotate((0, 0, 0), (1, 0, 0), -rot[0]).rotate((0, 0, 0), (0, 1, 0), -rot[1])
              .rotate((0, 0, 0), (0, 0, 1), -rot[2]).translate(off))
        top = round(float(sh.BoundingBox().zmax), 3)
    except Exception:
        top = None
    if top is not None and top <= 0.05:
        top = None                                   # model below the board: unusable
    _step_height_cache[key] = top
    try:
        disk[key] = top
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(disk, indent=0))
    except Exception:
        pass
    return top


def footprint_height_mm(
    footprint,
    *,
    assume_mm: float = 2.0,
) -> tuple[float, str]:
    """Best-known height (mm) for `footprint` + its source tag.

    Returns ``(height_mm, source)`` where source is "datasheet", "name", "model", or
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
    mh = model_top_mm(footprint)
    if mh is not None:
        return mh, "model"
    return assume_mm, "assumed"
