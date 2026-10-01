"""S-expression → dataclass interpreters for Specctra DSN.

Ported from `tools/dsn-validate/lib/sexp-to-json-interpreters/*.ts`.
Each interpreter takes a list-form s-expression slice (the `key`-tag
already stripped at the call site) and returns the corresponding
dataclass instance.

Naming mirrors the TS originals (`parse_sexpr_<section>`) so a diff
against the upstream reference stays readable.
"""

from __future__ import annotations

from smash.validators.specctra._schema import (
    Parser, Resolution, Structure, Layer, Keepout, Via, Rule,
    Clearance, LengthRule, Control, AutorouteSettings, LayerRule,
    ComponentPlacement, Place, PinPlacement,
    Image, ImagePin, Padstack, LibraryEntry,
    Network, Net, ViaRule, Class,
    Wiring, Wire,
    Circle, Rect, PathShape, Polygon,
)


SHAPE_NAMES = {"rect", "circle", "polygon", "path", "polyline_path"}


def _on_off(value):
    if value == "on":
        return True
    if value == "off":
        return False
    return value


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return s


def _to_coords(data):
    """Pair successive `[x, y, x, y, ...]` tokens into [(x, y), ...]."""
    out = []
    for i in range(0, len(data) - 1, 2):
        out.append([_to_float(data[i]), _to_float(data[i + 1])])
    return out


# ── shape ───────────────────────────────────────────────────────────────


def parse_sexpr_shape(data):
    """data = [shape_type, layer, *shape_data]"""
    shape_type, layer, *shape_data = data
    if shape_type == "circle":
        circle = Circle(layer=layer, radius=_to_float(shape_data[0]))
        if len(shape_data) >= 3:
            circle.x = _to_float(shape_data[1])
            circle.y = _to_float(shape_data[2])
        return circle
    if shape_type == "rect":
        return Rect(
            layer=layer,
            coordinates=[
                [_to_float(shape_data[0]), _to_float(shape_data[1])],
                [_to_float(shape_data[2]), _to_float(shape_data[3])],
            ],
        )
    if shape_type in ("path", "polyline_path"):
        return PathShape(
            layer=layer,
            width=_to_float(shape_data[0]),
            coordinates=_to_coords(shape_data[1:]),
        )
    if shape_type == "polygon":
        # Odd-count tail → first element is aperture width
        has_aperture = len(shape_data) % 2 == 1
        aperture = _to_float(shape_data[0]) if has_aperture else None
        start = 1 if has_aperture else 0
        return Polygon(
            layer=layer,
            coordinates=_to_coords(shape_data[start:]),
            aperture_width=aperture,
        )
    raise ValueError(f"unexpected shape type: {shape_type!r}")


# ── keepout ─────────────────────────────────────────────────────────────


def parse_sexpr_keepout(value):
    keepout_id = None
    if value and isinstance(value[0], str):
        keepout_id = value[0]
        value = value[1:]
    shape = None
    clearance_class = None
    for v in value:
        if not isinstance(v, list):
            continue
        key, *rest = v
        if key in SHAPE_NAMES:
            shape = parse_sexpr_shape([key, *rest])
        elif key == "clearance_class":
            clearance_class = rest[0]
    if shape is None:
        raise ValueError("keepout missing shape element")
    return Keepout(shape=shape, id=keepout_id, clearance_class=clearance_class)


# ── rule ────────────────────────────────────────────────────────────────


def parse_sexpr_rule(value):
    rule = Rule()
    extras: dict = {}
    for v in value:
        if not isinstance(v, list):
            continue
        key, *rest = v
        if key == "width":
            rule.width = _to_float(rest[0])
        elif key in ("clearance", "clear"):
            if rule.clearances is None:
                rule.clearances = []
            clr = Clearance(value=_to_float(rest[0]))
            if len(rest) > 1 and isinstance(rest[1], list) and rest[1][0] == "type":
                clr.type = rest[1][1]
            rule.clearances.append(clr)
        else:
            extras[key] = rest[0] if len(rest) == 1 else rest
    return rule


# ── via ─────────────────────────────────────────────────────────────────


def _is_coordinates(values):
    if len(values) < 2:
        return False
    try:
        float(values[0]); float(values[1])
        return True
    except (TypeError, ValueError):
        return False


def parse_sexpr_via(value):
    if not value:
        raise ValueError("via array is empty")
    primary, *rest = value
    if not isinstance(primary, str):
        raise ValueError("first via element must be a padstack id (string)")
    result = Via(primary_padstack=primary)
    if _is_coordinates(rest):
        x, y, *properties = rest
        result.x = float(x); result.y = float(y)
        for item in properties:
            if not (isinstance(item, list) and len(item) >= 2):
                continue
            key, *sub = item
            if key == "net":
                result.net = sub[0]
                if len(sub) > 1:
                    result.net_code = sub[1]
            elif key == "type":
                result.via_type = sub[0]
            elif key == "clearance_class":
                result.clearance_class = sub[0]
    else:
        # spare padstack list
        str_vals = [v for v in rest if isinstance(v, str)]
        if len(str_vals) == 1:
            result.spare_padstacks = str_vals
        elif len(str_vals) == 2:
            result.spare_padstacks = [str_vals[0]]
            result.property = str_vals[1]
        else:
            result.spare_padstacks = str_vals
    return result


# ── parser ──────────────────────────────────────────────────────────────


def parse_sexpr_parser(elements):
    p = Parser()
    for entry in elements:
        if not isinstance(entry, list):
            continue
        key, *vals = entry
        if key == "space_in_quoted_tokens":
            p.space_in_quoted_tokens = _on_off(vals[0])
        elif key == "host_cad":
            p.host_cad = vals[0]
        elif key == "host_version":
            p.host_version = vals[0]
        elif key == "constant" and vals and isinstance(vals[0], list):
            p.constant = p.constant or {}
            p.constant[vals[0][0]] = vals[0][1]
        elif key == "generated_by_freeroute":
            p.generated_by_freeroute = True
    return p


# ── structure (layer / boundary / control / autoroute) ──────────────────


def _parse_layer(value):
    name = value[0]
    layer = Layer(name=name, type="")
    for prop in value[1:]:
        if not isinstance(prop, list):
            continue
        k, *v = prop
        if k == "type":
            layer.type = v[0]
        elif k == "property" and v and isinstance(v[0], list):
            layer.properties = layer.properties or {}
            for sub in v:
                if isinstance(sub, list) and len(sub) >= 2:
                    layer.properties[sub[0]] = sub[1]
    return layer


def _parse_boundary(value):
    """`value` is the contents inside `(boundary (path ...))` — usually
    a single `(path ...)` or `(rect ...)` shape element."""
    if not isinstance(value, list) or not value:
        raise ValueError("boundary requires a shape element")
    return parse_sexpr_shape(value)


def _parse_control(value):
    ctrl = Control()
    for v in value:
        if not isinstance(v, list):
            continue
        k, *rest = v
        setattr(ctrl, k if hasattr(ctrl, k) else "_extra", _on_off(rest[0]) if rest else None)
    return ctrl


def _parse_autoroute_settings(value):
    settings = {}
    layer_rules = []
    for v in value:
        if not isinstance(v, list):
            continue
        k, *rest = v
        if k == "layer_rule":
            name = rest[0]
            lr = {"name": name}
            for setting in rest[1:]:
                if isinstance(setting, list) and len(setting) >= 2:
                    sk, sv = setting[0], setting[1]
                    try:
                        lr[sk] = float(sv)
                    except (TypeError, ValueError):
                        lr[sk] = sv
            layer_rules.append(lr)
        else:
            v0 = rest[0] if rest else None
            try:
                settings[k] = float(v0)
            except (TypeError, ValueError):
                settings[k] = _on_off(v0)
    # Build the dataclass with default-None for unfilled fields
    return AutorouteSettings(
        fanout=settings.get("fanout"),
        autoroute=settings.get("autoroute"),
        postroute=settings.get("postroute"),
        vias=settings.get("vias"),
        via_costs=settings.get("via_costs", 0.0),
        plane_via_costs=settings.get("plane_via_costs", 0.0),
        start_ripup_costs=settings.get("start_ripup_costs", 0.0),
        start_pass_no=settings.get("start_pass_no", 0.0),
        layer_rule=[LayerRule(**lr) for lr in layer_rules]
            if layer_rules else [],
    )


def parse_sexpr_structure(elements):
    struct = Structure(layers=[], boundaries=[])
    for element in elements:
        if not isinstance(element, list):
            continue
        key, *value = element
        if key == "layer":
            struct.layers.append(_parse_layer(value))
        elif key == "boundary":
            # value is one element wrapping a shape: `(path ...)` etc.
            struct.boundaries.append(_parse_boundary(value[0]))
        elif key == "keepout":
            if struct.keepouts is None:
                struct.keepouts = []
            struct.keepouts.append(parse_sexpr_keepout(value))
        elif key == "via":
            struct.via = parse_sexpr_via(value)
        elif key == "rule":
            struct.rules.append(parse_sexpr_rule(value))
        elif key == "control":
            struct.control = _parse_control(value)
        elif key == "autoroute_settings":
            struct.autoroute_settings = _parse_autoroute_settings(value)
        elif key == "snap_angle":
            struct.snap_angle = value[0]
        else:
            struct.extras[key] = value[0] if len(value) == 1 else value
    return struct


# ── placement ───────────────────────────────────────────────────────────


def _parse_place(place_elem):
    """`place_elem` looks like ['place', component_id, x, y, side, rotation, *properties]"""
    _, comp_id, x, y, side, rotation, *properties = place_elem
    place = Place(
        component_id=comp_id,
        x=_to_float(x), y=_to_float(y),
        side=side,
        rotation=_to_float(rotation),
    )
    for prop in properties:
        if not isinstance(prop, list):
            continue
        if prop[0] == "PN":
            place.part_number = prop[1]
        elif prop[0] == "pin":
            place.pins = place.pins or []
            place.pins.append(PinPlacement(
                pin_id=prop[1],
                clearance_class=prop[2][1] if isinstance(prop[2], list) else "",
            ))
    return place


def parse_sexpr_placement(elements):
    placement = []
    for element in elements:
        if not isinstance(element, list):
            continue
        kind, name, *places = element
        if kind != "component":
            continue
        placement.append(ComponentPlacement(
            component=name,
            places=[_parse_place(p) for p in places],
        ))
    return placement


# ── library (image / padstack) ──────────────────────────────────────────


def _parse_image_pin(data):
    pin = ImagePin(name=data[0], pin_number="", x=0.0, y=0.0)
    if len(data) > 1 and isinstance(data[1], list) and data[1][0] == "rotate":
        pin.rotate = _to_float(data[1][1])
        # remaining: [name, (rotate N), pin_number, x, y]
        if len(data) >= 5:
            pin.pin_number = data[2]
            pin.x = _to_float(data[3])
            pin.y = _to_float(data[4])
    else:
        if len(data) >= 4:
            pin.pin_number = data[1]
            pin.x = _to_float(data[2])
            pin.y = _to_float(data[3])
    return pin


def _parse_image(value):
    name, *elements = value
    img = Image(name=name, outlines=[], pins=[])
    for element in elements:
        if not isinstance(element, list):
            continue
        k, *data = element
        if k == "side":
            img.side = data[0]
        elif k == "outline":
            img.outlines.append(parse_sexpr_shape(data[0]))
        elif k == "pin":
            img.pins.append(_parse_image_pin(data))
        elif k == "keepout":
            img.keepouts = img.keepouts or []
            img.keepouts.append(parse_sexpr_keepout(data))
    return img


def _parse_padstack(value):
    name, *elements = value
    ps = Padstack(name=name, shapes=[])
    for element in elements:
        if not isinstance(element, list):
            continue
        k, *data = element
        if k == "shape":
            ps.shapes.append(parse_sexpr_shape(data[0]))
        elif k == "attach":
            ps.attach = data[0]
    return ps


def parse_sexpr_library(elements):
    library: list = []
    for element in elements:
        if not isinstance(element, list):
            continue
        k, *value = element
        if k == "image":
            library.append(LibraryEntry(image=_parse_image(value)))
        elif k == "padstack":
            library.append(LibraryEntry(padstack=_parse_padstack(value)))
    return library


# ── network ─────────────────────────────────────────────────────────────


def _parse_net(data):
    net = Net(name=data[0], pins=[])
    pins_index = 1
    if len(data) > 1 and isinstance(data[1], str):
        net.net_number = data[1]
        pins_index = 2
    for item in data[pins_index:]:
        if isinstance(item, list) and item and item[0] == "pins":
            net.pins = list(item[1:])
            break
    return net


def _parse_class(data):
    name = data[0]
    cls = Class(name=name, nets=[])
    for item in data[1:]:
        if isinstance(item, list):
            kind = item[0]
            if kind == "circuit":
                cls.circuit = {}
                for sub in item[1:]:
                    if isinstance(sub, list):
                        k, *vals = sub
                        cls.circuit[k] = vals[0] if len(vals) == 1 else list(vals)
            elif kind == "rule":
                cls.rule = parse_sexpr_rule(item[1:])
            elif kind == "clearance_class":
                cls.clearance_class = item[1]
            elif kind == "via_rule":
                cls.via_rule = item[1]
        elif item != "":
            cls.nets.append(item)
    return cls


def parse_sexpr_network(elements):
    network = Network(nets=[], vias=[], via_rules=[], classes=[])
    for element in elements:
        if not isinstance(element, list):
            continue
        kind, *data = element
        if kind == "net":
            network.nets.append(_parse_net(data))
        elif kind == "via":
            network.vias.append(parse_sexpr_via(data))
        elif kind == "via_rule":
            network.via_rules.append(ViaRule(name=data[0], via=data[1]))
        elif kind == "class":
            network.classes.append(_parse_class(data))
    return network


# ── wiring ──────────────────────────────────────────────────────────────


def _parse_wire(data):
    shape = None
    net = ""
    wire_type = None
    clearance_class = None
    for item in data:
        if not isinstance(item, list):
            continue
        k, *vals = item
        if k in SHAPE_NAMES:
            shape = parse_sexpr_shape([k, *vals])
        elif k == "net":
            net = vals[0]
        elif k == "type":
            wire_type = vals[0]
        elif k == "clearance_class":
            clearance_class = vals[0]
    if shape is None:
        raise ValueError("wire missing shape element")
    return Wire(shape=shape, net=net, type=wire_type,
                clearance_class=clearance_class)


def parse_sexpr_wiring(elements):
    wiring = Wiring(wires=[], vias=[])
    for element in elements:
        if not isinstance(element, list):
            continue
        kind, *data = element
        if kind == "wire":
            wiring.wires.append(_parse_wire(data))
        elif kind == "via":
            wiring.vias.append(parse_sexpr_via(data))
    return wiring
