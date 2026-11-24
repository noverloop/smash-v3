"""Design-audit regressions: the classes of schematic bug that kill a first
prototype and that ERC cannot see.

  * footprint winding — every perimeter footprint (QFN/DFN/SON/LGA/SOT/SOP)
    numbers its pins counter-clockwise in TOP view. A clockwise one is a
    mirrored land (smash pads are y-up; the KiCad exporter flips once).
  * STM32 ball map — every STM32 pin sits on the ball CubeMX says: supply
    balls on supplies, ground balls on ground, GPIO balls on that GPIO.
  * peripheral pins — the nets that need a hardware peripheral land on a pin
    that offers it in CubeMX (ADC input, OCTOSPI, SPI/UART/I2C/CAN).
"""
from __future__ import annotations

import contextlib
import glob
import io
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from smash.roots import git_repo_root

CUBEMX_DB = Path("/Applications/STMicroelectronics/STM32CubeMX.app/Contents/Resources/db/mcu")


@pytest.fixture(scope="module")
def design():
    root = str(git_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    import generate_devboard as GD
    with contextlib.redirect_stdout(io.StringIO()):
        d, _removed, _locks = GD.build_design()
    return d


def _net(pin):
    n = pin.net
    return getattr(n, "name", n)


# ── footprint winding ─────────────────────────────────────────────────────

def _signed_area(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2


def _winding(fp):
    """+1 counter-clockwise, −1 clockwise (top view, y-up), None if the
    footprint is not a perimeter package (connector rows, BGA, 2-3 pins)."""
    pads = {}
    for p in fp.pads:
        if str(p.num).isdigit():
            pads.setdefault(int(p.num), tuple(p.position_mm))
    pts = [pads[n] for n in sorted(pads) if math.hypot(*pads[n]) > 0.05]   # drop the centre EP
    if len(pts) < 4:
        return None
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    if min(w, h) < 0.2:                 # single row
        return None
    on_edge = all(min(abs(x - min(xs)), abs(x - max(xs)), abs(y - min(ys)), abs(y - max(ys)))
                  < 0.15 * max(w, h) + 0.05 for x, y in pts)
    a = _signed_area(pts)
    if not on_edge or abs(a) / (w * h) < 0.3:    # zig-zag header numbering
        return None
    return 1 if a > 0 else -1


def test_perimeter_footprints_wind_counter_clockwise(design):
    bad = {}
    for c in design.chips:
        fp = c.footprint
        if fp is None or not fp.pads:
            continue
        if _winding(fp) == -1:
            bad.setdefault(fp.name, []).append(c.ref)
    assert not bad, f"mirrored lands (pins wind clockwise in top view): {bad}"


def test_every_footprint_generator_winds_counter_clockwise():
    """Also the generators no part uses yet — the next caller inherits them."""
    import importlib
    import inspect
    import pkgutil
    import smash.parts as P
    bad = []
    for m in pkgutil.iter_modules(P.__path__):
        mod = importlib.import_module(f"smash.parts.{m.name}")
        for name, fn in vars(mod).items():
            if not (callable(fn) and name.endswith("footprint") and inspect.isfunction(fn)):
                continue
            if getattr(fn, "__module__", "") != mod.__name__:
                continue
            try:
                if any(p.default is p.empty for p in inspect.signature(fn).parameters.values()):
                    continue
                fp = fn()
            except Exception:
                continue
            if getattr(fp, "pads", None) and _winding(fp) == -1:
                bad.append(f"{m.name}.{name} ({fp.name})")
    assert not bad, f"mirrored footprint generators: {bad}"


# ── STM32 ball map vs CubeMX ──────────────────────────────────────────────

def _cubemx_xml(pn: str) -> Path | None:
    m = re.match(r"(STM32\w+?)(\d)(Q?)$", pn)
    if not m:
        return None
    f = CUBEMX_DB / f"{m.group(1)}x{m.group(3)}.xml"
    return f if f.exists() else None


def _cubemx_pins(xml: Path) -> dict:
    ns = {"m": "http://dummy.com"}
    tree = ET.parse(xml)
    out = {}
    for el in tree.getroot().iter():
        if el.tag.endswith("Pin") and "Position" in el.attrib:
            sigs = [s.attrib.get("Name", "") for s in el if s.tag.endswith("Signal")]
            out[el.attrib["Position"]] = (el.attrib["Name"], el.attrib.get("Type", ""), sigs)
    return out


def _stm32s(design):
    if not CUBEMX_DB.exists():
        pytest.skip("STM32CubeMX database not installed")
    return [(c, _cubemx_pins(x)) for c in design.chips
            if (c.manf_pn or "").startswith("STM32") and (x := _cubemx_xml(c.manf_pn))]


def test_stm32_balls_match_cubemx(design):
    errs = []
    for c, db in _stm32s(design):
        for p in c.pins:
            if p.num not in db:
                continue
            name, typ, _ = db[p.num]
            net = _net(p) or ""
            gnd = "GND" in net
            if name.startswith("VSS") and net and not gnd:
                errs.append(f"{c.ref}.{p.num} is {name} in CubeMX but on {net}")
            elif typ == "Power" and not name.startswith(("VSS", "VREF-")) and gnd:
                errs.append(f"{c.ref}.{p.num} is {name} in CubeMX but on {net}")
            m = re.match(r"P[A-Z]\d+", name)
            if m and not re.match(re.escape(m.group(0)) + r"(?!\d)", p.name):
                errs.append(f"{c.ref}.{p.num} is {name} in CubeMX but named {p.name}")
    assert not errs, "\n".join(errs)


# ── peripheral functions on the chosen pins ───────────────────────────────

def test_stm32_function_map(design):
    """smash.validators.stm32_functions: each peripheral net on a pin that
    offers it (F1), no signal on two pins (F2), one instance per bus (F3),
    EXTI lines within capacity (F4), boot-ROM UART TX pins harmless (F5)."""
    if not CUBEMX_DB.exists():
        pytest.skip("STM32CubeMX database not installed")
    from smash.validators.stm32_functions import check
    errs = check(design)
    assert not errs, "\n".join(errs)


# ── schematic ↔ PCB links in the exported packages ───────────────────────

def _footprint_links(pcb: Path, sch: Path):
    text = pcb.read_text()
    uuids = set(re.findall(r'\(uuid "([^"]+)"\)', sch.read_text()))
    out = {}
    for block in text.split("\n\t(footprint ")[1:]:
        ref = re.search(r'"Reference" "([^"]+)"', block)
        path = re.search(r'\(path "([^"]+)"\)', block)
        if ref and path:
            out[ref.group(1)] = path.group(1).split("/")[-1] in uuids
    return out


@pytest.mark.parametrize("stem", ["Smash", "dev_board/dev_board"])
def test_exported_footprints_link_to_their_symbols(stem):
    """Update PCB from Schematic pairs footprints with symbols by (path …):
    a path that names no symbol uuid makes KiCad delete + re-add the part."""
    root = git_repo_root() / "Unrouted"
    dates = sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit())
    if not dates:
        pytest.skip("no Unrouted export")
    pcb, sch = dates[-1] / f"{stem}.kicad_pcb", dates[-1] / f"{stem}.kicad_sch"
    links = _footprint_links(pcb, sch)
    bad = sorted(r for r, ok in links.items() if not ok)
    assert links and not bad, f"{len(bad)}/{len(links)} footprints link to no symbol: {bad[:10]}"


def test_every_pin_has_a_pad(design):
    """A vendored footprint whose pads the parser skipped (e.g. SnapMagic
    roundrect pads with (roundrect_rratio …) before (at …)) leaves pins with no
    copper — the part is placed but never connected."""
    bad = []
    for c in design.chips:
        fp = c.footprint
        if fp is None or not fp.pads:
            continue
        pads = {str(p.num) for p in fp.pads}
        miss = [p.num for p in c.pins
                if str(p.num) not in pads and str(p.num).removeprefix("BALL_") not in pads]
        if miss:
            bad.append(f"{c.ref} ({c.manf_pn}, {fp.name}): {len(miss)} pins without a pad, e.g. {miss[:5]}")
    assert not bad, "\n".join(bad)


# ── library check: every IC against its datasheet pinspec ─────────────────

# manf_pn → why it has no pinspec (checked another way, or not yet)
PINSPEC_EXEMPT = {
    "STM32MP257FAL3": "ball map checked against CubeMX (test_stm32_balls_match_cubemx)",
    "STM32WBA55UGI7": "ball map checked against CubeMX",
    "STM32U545REI6Q": "ball map checked against CubeMX",
    "STM32U535CBU6": "ball map checked against CubeMX",
    "MT41K256M16TW-107 IT:P": "compute board: manual / vendor check pending",
    "MT29F4G01ABAFDWB-IT_F": "compute board: manual / vendor check pending",
    "VB1943CAJX/1": "camera board: manual / vendor check pending",
    "LP5907MFX-2.8/NOPB": "camera board (DNP): manual check pending",
    "DSC1001CI1-027.0000": "camera board: manual check pending",
    "SIT1533AI-H4-DCC-32.768E": "compute board: manual check pending",
}


def _is_ic(c) -> bool:
    """Every part whose pin order matters: ICs, transistors, diodes, oscillators,
    transformers/baluns and connectors with an orderable part number."""
    if c.footprint is None:
        return False
    if re.match(r"(U|Y|Q|D)_|QHOLD|QMAIN", c.ref):
        return True
    return bool(re.match(r"(J|T)_", c.ref)) and bool(c.manf_pn) and not c.ref.startswith("J_CAST")


def test_every_ic_matches_its_pinspec(design):
    from smash.parts._pinspec import load_pinspec, compare
    missing, bad = set(), []
    for c in design.chips:
        if not _is_ic(c) or c.manf_pn in PINSPEC_EXEMPT:
            continue
        spec = load_pinspec(c.manf_pn)
        if spec is None:
            missing.add(c.manf_pn)
            continue
        for rule, msg in compare(c, spec):
            if rule != "pinspec_type_mismatch":      # types: separate pass
                bad.append(f"{c.ref} ({c.manf_pn}) {rule}: {msg}")
    assert not missing, f"ICs without a datasheet pinspec: {sorted(missing)}"
    assert not bad, "\n".join(bad)
