"""Helpers for reading SamacSys-generated artifacts directly.

The authoritative ground-truth for a part's pin numbering + name is its
KiCad symbol (`.kicad_sym`), not the project's `pinmap.txt` sidecar —
the sidecar passes pin names through an ASCII-cleaner that mangles
characters like `+` on `+IN` to `PIN` (caught on AD8603). Factories
parse the KiCad sym directly.

For footprints, the same applies — the `.kicad_mod` is what the layout
engine consumes, so parsing it directly keeps the Footprint.pads list
byte-for-byte consistent with what will be on the board.

Both readers cache by absolute path so repeated calls are cheap.
"""

from __future__ import annotations

import functools
import pathlib
import re

from smash.state import Pad


# Resolve artifact paths relative to this module so factories don't
# depend on Python's CWD. `sources/<PN>/...` is the canonical layout.
SOURCES_DIR = (pathlib.Path(__file__).parent / "sources").resolve()


def src(part_dir: str, filename: str) -> str:
    """Build an absolute path to `sources/<part_dir>/<filename>`."""
    return str(SOURCES_DIR / part_dir / filename)


def datasheet_ref(part_dir: str, filename: str) -> str:
    """Build a repo-relative path string suitable for the `datasheet`
    field on Chip/Battery (so `REPO_ROOT / chip.datasheet` resolves
    in tests)."""
    return f"application/src/smash/parts/sources/{part_dir}/{filename}"


# ─── KiCad symbol pin parser ─────────────────────────────────────────────

_PIN_HEADER_RX = re.compile(
    r"\(pin\s+(?P<elec>\w+)\s+(?P<shape>\w+)\s")
_NAME_RX   = re.compile(r'\(name\s+"(?P<v>[^"]*)"')
_NUMBER_RX = re.compile(r'\(number\s+"(?P<v>[^"]*)"')


@functools.lru_cache(maxsize=None)
def _read_text(path: str) -> str:
    return pathlib.Path(path).read_text()


def _balanced_span(text: str, start: int) -> int:
    """Return the index just past the `)` that balances the `(` at
    text[start]. Raises ValueError if unbalanced."""
    if text[start] != "(":
        raise ValueError(f"expected '(' at {start}, got {text[start]!r}")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced parens")


def pins_from_kicad_sym(kicad_sym_path: str) -> list[tuple[str, str, str]]:
    """Parse a KiCad 6+ `.kicad_sym` file and return a list of
    `(number, name, elec_type)` tuples — one per `(pin ...)` entry,
    in document order.

    `elec_type` is the KiCad pin electrical class as written by
    SamacSys ('passive', 'power_in', 'input', etc.). It is NOT the
    schema's `Pin.type` token; factories supply that via overlay.
    """
    text = _read_text(kicad_sym_path)
    out = []
    i = 0
    while True:
        m = _PIN_HEADER_RX.search(text, i)
        if not m:
            break
        block_start = m.start()
        block_end = _balanced_span(text, block_start)
        block = text[block_start:block_end]
        elec = m.group("elec")
        name_m = _NAME_RX.search(block)
        num_m  = _NUMBER_RX.search(block)
        if num_m:
            out.append((num_m.group("v"),
                        name_m.group("v") if name_m else "",
                        elec))
        i = block_end
    return out


# ─── KiCad footprint (mod) parser ────────────────────────────────────────

_PAD_RX = re.compile(
    r"""\(pad\s+
        (?P<num>\S+)\s+               # pin number/name (can be quoted)
        (?P<class>\w+)\s+             # smd | thru_hole | np_thru_hole | connect
        (?P<shape>\w+)\s+             # rect | circle | oval | roundrect | custom
        \(at\s+(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)
                  (?:\s+(?P<rot>-?\d+(?:\.\d+)?))?\s*\)\s+
        \(size\s+(?P<w>-?\d+(?:\.\d+)?)\s+(?P<h>-?\d+(?:\.\d+)?)\s*\)
        (?:\s+\(drill\s+(?:oval\s+)?(?P<drill>-?\d+(?:\.\d+)?)
                  (?:\s+-?\d+(?:\.\d+)?)?\s*\))?   # (drill N) or (drill oval W H)
        [^)]*\(layers\s+(?P<layers>[^)]+)\)
    """,
    re.VERBOSE,
)

_FP_LINE_RX = re.compile(
    r"""\(fp_line\s+
        \(start\s+(?P<x1>-?\d+(?:\.\d+)?)\s+(?P<y1>-?\d+(?:\.\d+)?)\)\s+
        \(end\s+(?P<x2>-?\d+(?:\.\d+)?)\s+(?P<y2>-?\d+(?:\.\d+)?)\)\s+
        \(layer\s+(?P<layer>\S+)\)
    """,
    re.VERBOSE,
)


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def pads_from_kicad_mod(kicad_mod_path: str) -> list[Pad]:
    """Parse a KiCad `.kicad_mod` (footprint) file and return the Pad
    list in document order.

    Layers are passed through verbatim; the primary copper layer of
    a pad is the first F.Cu or B.Cu entry in the `(layers ...)` list.
    Drill is set for through-hole pads only.
    """
    text = _read_text(kicad_mod_path)
    out: list[Pad] = []
    for m in _PAD_RX.finditer(text):
        layers = m.group("layers").split()
        # Pick the first copper layer as the primary
        primary = next((L for L in layers if L.endswith("Cu")), layers[0])
        # The model's Pad has no rotation field, so a pad's own rotation
        # must be baked into its size: a 90°/270° pad's (size w h) renders
        # as an h-wide × w-tall envelope (pcbnew-verified). SamacSys mods
        # rotate the lead pads of most SOT/SOIC/SON packages this way —
        # reading (w, h) verbatim swapped every such pad's aspect.
        w, h = float(m.group("w")), float(m.group("h"))
        rot = float(m.group("rot") or 0.0)
        if rot % 180 == 90:
            w, h = h, w
        out.append(Pad(
            num=_strip_quotes(m.group("num")),
            # KiCad `.kicad_mod` files are screen-y-down; the smash model
            # is math-y-up (the kicad_pcb exporter flips Y once at the
            # boundary). Convert here on import so imported footprints share
            # the y-up convention with hand-authored ones — otherwise the
            # exporter's flip mirrors them vertically (e.g. the DDR4 BGA
            # ball map ends up flipped top-to-bottom).
            position_mm=(float(m.group("x")), -float(m.group("y"))),
            size_mm=(w, h),
            shape=m.group("shape"),
            layer=primary,
            drill_mm=(float(m.group("drill")) if m.group("drill") else None),
        ))
    return out


def fp_lines_on_layer(kicad_mod_path: str, layer: str) -> list[tuple[tuple, tuple]]:
    """Return `[((x1,y1), (x2,y2)), ...]` for every `(fp_line ...)` on
    the given KiCad layer. Use this to extract body outline (F.Fab)
    or courtyard (F.CrtYd) polygons.
    """
    text = _read_text(kicad_mod_path)
    out = []
    for m in _FP_LINE_RX.finditer(text):
        if m.group("layer") == layer:
            # y-down (KiCad) → y-up (smash model); see pads_from_kicad_mod.
            out.append((
                (float(m.group("x1")), -float(m.group("y1"))),
                (float(m.group("x2")), -float(m.group("y2"))),
            ))
    return out


def outline_polygon(kicad_mod_path: str, layer: str) -> list[tuple[float, float]]:
    """Return a closed polygon of (x, y) vertices for the outline on
    the given layer. Assumes the layer's fp_lines form a single
    closed loop (typical for F.Fab body outline and F.CrtYd
    courtyard — SamacSys-generated mods always do this).

    Returns vertices in document order without duplicating the closing
    point. If the layer has no fp_lines, returns an empty list.
    """
    lines = fp_lines_on_layer(kicad_mod_path, layer)
    if not lines:
        return []
    verts = [lines[0][0]]
    for (a, b) in lines:
        # If the line's start matches the last vertex, append the end
        if verts[-1] == a:
            verts.append(b)
        elif verts[-1] == b:
            verts.append(a)
        else:
            # Disjoint segment — just append the start as a new vertex
            verts.append(a)
    # Drop the closing duplicate if the loop closed
    if len(verts) > 1 and verts[0] == verts[-1]:
        verts.pop()
    return verts


# ─── Pin-building convenience ────────────────────────────────────────────

def build_pins(kicad_sym_path: str, *,
               types: dict | None = None,
               aliases: dict | None = None,
               notes: dict | None = None,
               voltage_domains: dict | None = None) -> list:
    """Build a Pin list from a KiCad symbol with per-pin metadata
    overlays. Each overlay dict keys by pin number (datasheet pad
    position, e.g. "K10" or "1") or by pin name (datasheet primary
    name).

    Example:
        pins = build_pins(
            "parts/sources/U1/U1.kicad_sym",
            types={"1": "ground", "8": "power"},
            aliases={"3": ["DATA_IN", "SI"]},
            notes={"6": "active-low, requires pull-up"},
        )
    """
    from smash.state import Pin
    types = types or {}
    aliases = aliases or {}
    notes = notes or {}
    voltage_domains = voltage_domains or {}

    raw_pins = list(pins_from_kicad_sym(kicad_sym_path))

    # Pre-collect all primary pin names in this part so the
    # double-underscore-collapse pass can detect collisions.
    primary_names = {name for _num, name, _elec in raw_pins}

    # Pre-collect all single-underscore-collapse candidates and detect
    # the case where two distinct double-underscore names collapse to
    # the SAME single-underscore form (would create an ambiguous alias).
    collapsed_counts: dict[str, int] = {}
    for _num, name, _elec in raw_pins:
        if "__" in name:
            c = name.replace("__", "_")
            if c != name:
                collapsed_counts[c] = collapsed_counts.get(c, 0) + 1

    out = []
    for num, name, _elec in raw_pins:
        # Allow overlays keyed by either pin number or pin name
        for k in (num, name):
            if k in types or k in aliases or k in notes or k in voltage_domains:
                key = k
                break
        else:
            key = num
        chip_aliases = list(aliases.get(key, []))
        # SamacSys often uses double-underscore in pin names (e.g.
        # `VIDDA__10RF1`, `VOUT__14APLL`, `MSS_MIBSPIA__CS0`) where the
        # datasheet uses single-underscore. Auto-expose the single-
        # underscore variant as an alias so callers can use either form.
        # Skip the alias if it would collide with another pin's primary
        # name or with another collapsed candidate (ambiguous → leave
        # caller to use the verbatim double-underscore name).
        if "__" in name:
            collapsed = name.replace("__", "_")
            if (collapsed != name
                    and collapsed not in chip_aliases
                    and collapsed not in primary_names
                    and collapsed_counts.get(collapsed, 0) == 1):
                chip_aliases.append(collapsed)
        out.append(Pin(
            num=num,
            name=name,
            aliases=chip_aliases,
            type=types.get(key),
            voltage_domain=voltage_domains.get(key),
            note=notes.get(key),
        ))
    return out
