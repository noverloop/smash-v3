"""Specctra session (`.ses`) parser.

A routing session is what an autorouter (KiCad's Pcbnew, Freerouting,
Allegro) writes back after routing the `.dsn` we exported. Its grammar
differs from the input `.dsn` handled by `parse_dsn`:

    (session "name"
      (base_design "name")
      (placement (resolution um 10) (component ... (place REF x y side rot)))
      (routes
        (resolution um 10)
        (parser ...)
        (library_out (padstack NAME (shape (circle LAYER r x y)) ...) ...)
        (network_out
          (net "NAME"
            (wire (path LAYER WIDTH x y x y ...))
            (via "PADSTACK" x y)
            ...))))

The leaf forms — `(wire (path ...))`, `(via PADSTACK x y)`, `(padstack
...)` — are identical to the `.dsn` ones, so we reuse the existing
`_interpreters` leaf parsers. Only the `(routes ...)` / `(network_out
...)` / per-`(net ...)` container is new here, and unlike the `.dsn`
wiring section the net name lives on the enclosing `(net ...)` rather
than inside each wire/via — we attach it as we walk.

`parse_session(source) -> Session` returns the parsed routing. The
conversion into native `Track`/`Via` (units → mm, Y-flip, per-board
localization) lives in `smash.state.routing.ingest`, which keeps this
module a pure parser like the rest of `validators.specctra`.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from smash.validators.specctra._sexp import parse_sexp
from smash.validators.specctra._schema import (
    Resolution, Padstack, Wire, Via, Wiring, ComponentPlacement,
)
from smash.validators.specctra._interpreters import (
    parse_sexpr_placement, _parse_padstack, _parse_wire, parse_sexpr_via,
)


@dataclasses.dataclass
class Session:
    """Parsed `.ses` routing session."""
    name: str
    resolution: Resolution
    unit: str
    padstacks: dict                     # name -> Padstack (from library_out)
    wiring: Wiring                      # wires + vias, each with .net set
    placement: list                     # list[ComponentPlacement] (may be empty)


def _load(source: str | Path) -> str:
    p = Path(source)
    try:
        if p.exists():
            return p.read_text()
    except OSError:
        pass
    return str(source)


def parse_session(source: str | Path) -> Session:
    """Parse a `.ses` routing session (path or raw text) into a
    `Session`. Raises `ValueError` if the top node isn't `(session ...)`
    or the required `(routes ...)` block is missing."""
    text = _load(source)
    sexp = parse_sexp(text)
    if not sexp or sexp[0] != "session":
        raise ValueError(
            f"top-level node must be `(session ...)`, got "
            f"{sexp[0] if sexp else 'empty'!r}"
        )
    name = sexp[1] if len(sexp) > 1 else ""

    resolution: Resolution | None = None
    unit = ""
    placement: list = []
    routes: list | None = None

    for element in sexp[2:]:
        if not isinstance(element, list) or not element:
            continue
        kind, *body = element
        if kind == "placement":
            placement = _parse_placement_block(body)
        elif kind == "routes":
            routes = body

    if routes is None:
        raise ValueError("session missing required `(routes ...)` block")

    padstacks: dict = {}
    wiring = Wiring(wires=[], vias=[])
    for element in routes:
        if not isinstance(element, list) or not element:
            continue
        kind, *body = element
        if kind == "resolution":
            resolution = Resolution(unit=body[0], value=float(body[1]))
            unit = body[0]
        elif kind == "library_out":
            for sub in body:
                if isinstance(sub, list) and sub and sub[0] == "padstack":
                    ps = _parse_padstack(sub[1:])
                    padstacks[ps.name] = ps
        elif kind == "network_out":
            _parse_network_out(body, wiring)

    if resolution is None:
        raise ValueError("session `(routes ...)` missing `(resolution ...)`")

    return Session(
        name=name, resolution=resolution, unit=unit,
        padstacks=padstacks, wiring=wiring, placement=placement,
    )


def _parse_placement_block(body: list) -> list:
    """`(placement (resolution ...) (component ...) ...)` — strip the
    leading resolution and hand the components to the shared placement
    interpreter."""
    components = [e for e in body
                  if isinstance(e, list) and e and e[0] == "component"]
    return parse_sexpr_placement(components)


def _parse_network_out(body: list, wiring: Wiring) -> None:
    """Walk `(network_out (net NAME (wire ...) (via ...) ...) ...)`,
    attaching each net's name to the wires/vias it contains (the `.ses`
    grouping carries the net at the `(net ...)` level, not per item)."""
    for element in body:
        if not isinstance(element, list) or not element or element[0] != "net":
            continue
        net_name = element[1] if len(element) > 1 else None
        for item in element[2:]:
            if not isinstance(item, list) or not item:
                continue
            kind, *data = item
            if kind == "wire":
                wire = _parse_wire(data)
                if not wire.net:
                    wire = Wire(shape=wire.shape, net=net_name,
                                type=wire.type,
                                clearance_class=wire.clearance_class)
                wiring.wires.append(wire)
            elif kind == "via":
                via = parse_sexpr_via(data)
                if via.net is None:
                    via.net = net_name
                wiring.vias.append(via)
