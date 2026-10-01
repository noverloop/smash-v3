"""Parser for the top-level `components.md` reference table.

Loads the main component table + the thermal-characteristics table
and returns a lookup dict keyed by part number (the **bold** part-name
in each row's first column).

Each entry carries the union of every field across the two tables;
fields not present in a given row come back as None.

Schema (per entry):
    {
        "name":           str,           # part number (table key)
        "function":       str | None,
        "board":          str | None,    # tile / sub-PCB name
        "critical":       bool | None,
        "package":        str | None,
        "size_mm":        (W, H) | None, # in mm (from "Size (mm)" column)
        "height_mm":      float | None,
        "weight_g":       float | None,
        "fab_location":   str | None,
        "temp_range_c":   (min, max) | None,
        "eccn":           str | None,
        "price_1pc_eur":  float | None,
        "price_20kpc_eur":float | None,
        "p_active_w":     float | None,  # from thermal table
        "p_max_w":        float | None,
        "rth_jc_cw":      float | None,
        "rth_ja_cw":      float | None,
        "tj_max_c":       float | None,
    }
"""

from __future__ import annotations

import pathlib
import re


def _find_components_md() -> pathlib.Path:
    """Search upward from this file for the project's components.md.

    The library can be installed anywhere; the file lives under the
    Smash project's `documentation/` directory. We walk ancestors,
    checking both `documentation/components.md` and a bare
    `components.md` (legacy root location). Callers that want a
    non-default location pass an explicit path to `parse(path)`.
    """
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        for candidate in (parent / "documentation" / "components.md",
                          parent / "components.md"):
            if candidate.exists():
                return candidate
    # Fallback to a deterministic relative path so a caller error-
    # message points at something concrete.
    return here.parents[3] / "documentation" / "components.md"


COMPONENTS_MD = _find_components_md()


_RX_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _strip_md(s: str) -> str:
    """Remove bold markers and surrounding whitespace from a cell."""
    return _RX_BOLD.sub(r"\1", s).strip()


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s or s.lower() in ("tbd", "tbq", "—", "-"):
        return None
    # Strip parenthetical qualifiers like "0.05 (write)" or "0.02 (RX)"
    s = re.sub(r"\(.*?\)", "", s).strip()
    # Take the first numeric token (handle "10*" → 10)
    m = re.match(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _parse_size(s: str) -> tuple | None:
    """'7×7' → (7.0, 7.0); '~6.3×5.1' → (6.3, 5.1); '9.9×3.9' → ..."""
    s = s.strip().lstrip("~")
    m = re.match(r"\s*([\d.]+)\s*[×x]\s*([\d.]+)", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


def _parse_temp(s: str) -> tuple | None:
    """'-40..+85' → (-40, 85). Returns None on '—', 'TBD', etc."""
    s = s.strip()
    m = re.match(r"\s*([-+]?\d+)\s*\.\.\s*([-+]?\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def _row_cells(line: str) -> list:
    """Strip leading/trailing pipes and split."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def parse(path: pathlib.Path = COMPONENTS_MD) -> dict:
    """Parse the markdown and return a dict keyed by part number."""
    if not path.exists():
        return {}
    text = path.read_text()
    out: dict = {}
    in_main = False
    in_thermal = False
    for line in text.splitlines():
        stripped = line.strip()
        # Detect the two header rows we care about; once seen, start
        # consuming the next non-separator rows.
        if "| Component | Function | Board | Critical | Package" in line:
            in_main = True
            in_thermal = False
            continue
        if "| Component (BOM ref Manf_PN) | Package | P_active" in line:
            in_thermal = True
            in_main = False
            continue
        # Stop on blank lines or new section headers.
        if not stripped or stripped.startswith("#"):
            in_main = in_thermal = False
            continue
        # Skip the markdown table separator row (`|---|---|...|`).
        if set(stripped) <= set("|-: "):
            continue
        if in_main and stripped.startswith("|"):
            cells = _row_cells(line)
            if len(cells) < 13:
                continue
            name_raw = cells[0]
            m = _RX_BOLD.search(name_raw)
            if not m:
                continue
            name = m.group(1).strip()
            entry = out.setdefault(name, {"name": name})
            entry.update({
                "function":       _strip_md(cells[1]) or None,
                "board":          _strip_md(cells[2]) or None,
                "critical":       cells[3].strip().lower() == "yes",
                "package":        _strip_md(cells[4]) or None,
                "size_mm":        _parse_size(cells[5]),
                "height_mm":      _parse_float(cells[6]),
                "weight_g":       _parse_float(cells[7]),
                "fab_location":   _strip_md(cells[8]) or None,
                "temp_range_c":   _parse_temp(cells[9]),
                "eccn":           _strip_md(cells[10]) or None,
                "price_1pc_eur":  _parse_float(cells[11]),
                "price_20kpc_eur":_parse_float(cells[12]),
            })
        elif in_thermal and stripped.startswith("|"):
            cells = _row_cells(line)
            if len(cells) < 8:
                continue
            name_raw = cells[0]
            m = _RX_BOLD.search(name_raw)
            if not m:
                continue
            name = m.group(1).strip()
            entry = out.setdefault(name, {"name": name})
            entry.update({
                "package":     entry.get("package") or _strip_md(cells[1]),
                "p_active_w":  _parse_float(cells[2]),
                "p_max_w":     _parse_float(cells[3]),
                "rth_jc_cw":   _parse_float(cells[4]),
                "rth_ja_cw":   _parse_float(cells[5]),
                "tj_max_c":    _parse_float(cells[6]),
            })
    return out
