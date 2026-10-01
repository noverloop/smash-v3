"""Dataclass schema for parsed Specctra DSN files.

Mirrors `tools/dsn-validate/lib/zod-schema.ts` field-for-field so the
TS reference (tscircuit/specctra-dsn-json) and this Python port stay in
lock-step. Validation isn't done via a schema library — each dataclass
carries the right `Optional`/`list` typing and the interpreters
populate required fields explicitly.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Union


# ── shapes ──────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Circle:
    layer: str
    radius: float
    x: Optional[float] = None
    y: Optional[float] = None
    aperture_width: Optional[float] = None
    type: str = "circle"


@dataclasses.dataclass
class Rect:
    layer: str
    coordinates: list   # [[x1, y1], [x2, y2]]
    aperture_width: Optional[float] = None
    type: str = "rect"


@dataclasses.dataclass
class PathShape:
    layer: str
    width: float
    coordinates: list   # [[x, y], ...]
    aperture_width: Optional[float] = None
    type: str = "path"


@dataclasses.dataclass
class Polygon:
    layer: str
    coordinates: list   # [[x, y], ...]
    aperture_width: Optional[float] = None
    type: str = "polygon"


Shape = Union[Circle, Rect, PathShape, Polygon]


# ── parser metadata ─────────────────────────────────────────────────────


@dataclasses.dataclass
class Parser:
    space_in_quoted_tokens: Optional[bool] = None
    host_cad: Optional[str] = None
    host_version: Optional[str] = None
    constant: Optional[dict] = None
    write_resolution: Optional[list] = None
    routes_include: Optional[list] = None
    wires_include: Optional[str] = None
    case_sensitive: Optional[bool] = None
    rotate_first: Optional[bool] = None
    generated_by_freeroute: Optional[bool] = None


# ── resolution / unit ───────────────────────────────────────────────────


@dataclasses.dataclass
class Resolution:
    unit: str
    value: float


# ── structure ───────────────────────────────────────────────────────────


@dataclasses.dataclass
class Layer:
    name: str
    type: str
    properties: Optional[dict] = None
    direction: Optional[str] = None         # "horizontal" | "vertical"
    cost: Optional[float] = None


@dataclasses.dataclass
class Keepout:
    shape: Shape
    id: Optional[str] = None
    aperture_width: Optional[float] = None
    clearance_class: Optional[str] = None


@dataclasses.dataclass
class Via:
    primary_padstack: str
    x: Optional[float] = None
    y: Optional[float] = None
    net: Optional[str] = None
    net_code: Optional[str] = None
    via_type: Optional[str] = None
    clearance_class: Optional[str] = None
    spare_padstacks: Optional[list] = None
    property: Optional[str] = None


@dataclasses.dataclass
class Clearance:
    value: float
    type: Optional[str] = None


@dataclasses.dataclass
class LengthRule:
    min: float
    max: float


@dataclasses.dataclass
class Rule:
    name: Optional[str] = None
    width: Optional[float] = None
    clearances: Optional[list] = None     # list[Clearance]
    length: Optional[LengthRule] = None
    via_costs: Optional[float] = None
    layer_change_costs: Optional[float] = None


@dataclasses.dataclass
class Control:
    via_at_smd: Optional[bool] = None
    off_grid_wires: Optional[bool] = None
    ignore_conduction: Optional[bool] = None
    fanout_direction: Optional[str] = None


@dataclasses.dataclass
class LayerRule:
    name: str
    active: Any
    preferred_direction: str
    preferred_direction_trace_costs: float
    against_preferred_direction_trace_costs: float


@dataclasses.dataclass
class AutorouteSettings:
    fanout: Any
    autoroute: Any
    postroute: Any
    vias: Any
    via_costs: float
    plane_via_costs: float
    start_ripup_costs: float
    start_pass_no: float
    layer_rule: list   # list[LayerRule]


@dataclasses.dataclass
class Structure:
    layers: list
    boundaries: list
    via: Optional[Via] = None
    rules: list = dataclasses.field(default_factory=list)
    keepouts: Optional[list] = None
    snap_angle: Optional[str] = None
    control: Optional[Control] = None
    autoroute_settings: Optional[AutorouteSettings] = None
    extras: dict = dataclasses.field(default_factory=dict)


# ── placement ───────────────────────────────────────────────────────────


@dataclasses.dataclass
class PinPlacement:
    pin_id: str
    clearance_class: str


@dataclasses.dataclass
class Place:
    component_id: str
    x: float
    y: float
    side: str   # "front" | "back"
    rotation: float
    part_number: Optional[str] = None
    pins: Optional[list] = None   # list[PinPlacement]


@dataclasses.dataclass
class ComponentPlacement:
    component: str
    places: list   # list[Place]


# ── library ─────────────────────────────────────────────────────────────


@dataclasses.dataclass
class ImagePin:
    name: str
    pin_number: str
    x: float
    y: float
    rotate: Optional[float] = None


@dataclasses.dataclass
class Image:
    name: str
    outlines: list   # list[Shape]
    pins: list       # list[ImagePin]
    keepouts: Optional[list] = None
    side: Optional[str] = None


@dataclasses.dataclass
class Padstack:
    name: str
    shapes: list   # list[Shape]
    attach: Optional[str] = None


# A library element is either {image: Image} or {padstack: Padstack}.
# We keep both fields nullable on a single dataclass for simplicity.
@dataclasses.dataclass
class LibraryEntry:
    image: Optional[Image] = None
    padstack: Optional[Padstack] = None


# ── network ─────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Net:
    name: str
    pins: list = dataclasses.field(default_factory=list)
    net_number: Optional[str] = None


@dataclasses.dataclass
class ViaRule:
    name: str
    via: str


@dataclasses.dataclass
class Class:
    name: str
    nets: list = dataclasses.field(default_factory=list)
    circuit: Optional[dict] = None
    rule: Optional[Rule] = None
    clearance_class: Optional[str] = None
    via_rule: Optional[str] = None


@dataclasses.dataclass
class Network:
    nets: Optional[list] = None
    vias: Optional[list] = None
    via_rules: Optional[list] = None
    classes: Optional[list] = None


# ── wiring ──────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Wire:
    shape: Shape
    net: str
    type: Optional[str] = None
    clearance_class: Optional[str] = None


@dataclasses.dataclass
class Wiring:
    wires: list = dataclasses.field(default_factory=list)
    vias: list = dataclasses.field(default_factory=list)


# ── top-level design ────────────────────────────────────────────────────


@dataclasses.dataclass
class DsnPcbDesign:
    pcb_id: str
    parser: Parser
    resolution: Resolution
    unit: str
    structure: Structure
    placement: list      # list[ComponentPlacement]
    library: list        # list[LibraryEntry]
    network: Network
    wiring: Wiring
