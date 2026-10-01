"""Per-layer 3D STEP + JSON manifest for FEA / EM-sim ingestion.

The existing `stackup_step.py` exports each rigid board as a *single*
FR4 disc — sufficient for the folded-tower mechanical model, but not
for a solver that needs per-layer material assignment. This module
walks `board.stackup` (Cu layers + their `dielectric_below`) and emits
ONE cadquery body per physical layer, tagged with name + material in
an assembly STEP and a sidecar JSON manifest with the layer's elastic
/ electrical properties resolved through the FabProfile catalog.

Output, per call to `write_layered_board_step(board, path, fab=…)`:

  <path>.step  — multi-body STEP assembly, one solid per layer:
                   - copper foils  (F.Cu, In1, In2, …, B.Cu)
                   - dielectric    (each Layer.dielectric_below)
                   - optional Al backing if board.al_backing_mm > 0
                   - optional chip body blocks (component masses)

  <path>.json  — body-name → material dict with everything the solver
                   needs to assign properties:
                     name, role, material, thickness_mm,
                     E_GPa, nu, rho_kg_m3,         (mechanical)
                     epsilon_r, loss_tangent,      (EM dielectric)
                     conductivity_S_m,             (EM conductor)
                     z_min_mm, z_max_mm            (Z extent)

Layer naming: `<board>.<layer_or_dielectric_id>`. So a 14-layer board
on an Eccobond-protected vacuum-pot results in ~30 bodies (14 Cu + 13
dielectrics + Al backing + chip blocks).
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

from smash.state import Chip
from smash.state.antenna import Antenna
from smash.layout.placer.grid import footprint_bbox_mm


# Copper bulk conductivity (5.96e7 S/m @ 20 °C). The fab profile carries
# `CopperFoil.conductivity_s_m` per foil; we use that when populated and
# fall back to this physical constant otherwise.
DEFAULT_COPPER_SIGMA_S_M = 5.96e7
DEFAULT_COPPER_E_GPA = 117.0
DEFAULT_COPPER_NU = 0.34
DEFAULT_COPPER_RHO = 8960.0

# Soldermask — liquid photoimageable solder mask (LPSM), epoxy-based,
# the green/blue/black coating on every finished PCB. Sits over the
# outer copper layers; permanent. Constants chosen for typical Taiyo
# / Peters LPSM at 25 °C, sub-GHz to mmWave:
#   ε_r ≈ 3.6-4.0 (DK rises slightly with humidity);
#   tan δ ≈ 0.020-0.030 (higher than FR4 at mmWave — matters for
#   surface impedance of mmWave traces);
#   κ_thermal ≈ 0.25 W/(m·K) — similar to FR4.
#   E ≈ 4 GPa, ρ ≈ 1400 kg/m³, ν ≈ 0.35 — cured epoxy.
# Per-side thickness is half of `Board.MASK_FINISH_MM` (which is
# total, top + bottom).
SOLDERMASK_EPSILON_R = 3.8
SOLDERMASK_LOSS_TANGENT = 0.025
SOLDERMASK_E_GPA = 4.0
SOLDERMASK_NU = 0.35
SOLDERMASK_RHO = 1400.0
SOLDERMASK_THERMAL_W_PER_MK = 0.25

# Via barrel — plated copper hole connecting layers. At GHz frequencies
# the skin depth in Cu is ~7 µm; standard plating is 25 µm; barrel is
# fully conductive (modeled as solid Cu cylinder, simpler than the
# hollow-shell geometry and gives the same EM answer for f > 1 GHz).
# Mechanical: tiny (small Cu plug through FR4). Thermal: significant
# (Cu κ = 400 vs FR4 κ = 0.3) — `Via.filled` boards get an additional
# resin column, but we keep both as solid Cu for now (filled vias
# only differ from open vias in via the resin's thermal κ ≈ 0.5).
VIA_PLATING_AS_SOLID_CU = True            # see comment above

# Soldermask "expansion" — the small gap by which the mask opening is
# made larger than the pad it sits over. Fab-specified per pad
# (`Pad.solder_mask_expansion_mm`); we fall back to this default when
# the pad doesn't set one. 0.05 mm is the typical HDI value (50 µm
# clearance prevents mask flowing onto the pad during cure).
DEFAULT_MASK_EXPANSION_MM = 0.05


# ── Cu coin geometry helpers ────────────────────────────────────────────
# A CuCoinInsert is a chamfered-rectangle Cu prism embedded in the
# board's stackup, replacing FR4 / Cu layers in its Z range. For the
# layered EM mesh the coin needs to appear as a Cu solid (the EM
# solver sees the low-impedance F.Cu→B.Cu shortcut it provides on
# radar / companion_compute), AND every overlapping FR4 / Cu layer
# needs its coin-footprint cut out so the geometry is non-overlapping.
def _coin_2d_footprint(coin):
    """Build the coin's chamfered-rectangle footprint as a cadquery
    sketch sized in the coin's LOCAL frame (rectangle centred at the
    origin, long axis along +X = NCAB Y direction). Caller rotates and
    translates the extruded body."""
    import cadquery as cq
    L = float(coin.length_mm)
    W = float(coin.width_mm)
    R = float(coin.corner_chamfer_radius_mm or 0.0)
    if R > 0:
        sketch = (cq.Sketch().rect(L, W).vertices().fillet(R))
        return cq.Workplane("XY").placeSketch(sketch)
    return cq.Workplane("XY").rect(L, W)


def _coin_extruded_body(coin, *, thickness_mm: float, base_z_mm: float):
    """A solid extrusion of the coin's 2D footprint at `base_z_mm`,
    extending up by `thickness_mm`, rotated by `coin.rotation_deg` and
    translated to `coin.position_mm`. Used both as the coin's own Cu
    body and as the cutting stamp on any layer the coin straddles."""
    px, py = coin.position_mm
    body = _coin_2d_footprint(coin).extrude(thickness_mm)
    if coin.rotation_deg:
        body = body.rotate((0, 0, 0), (0, 0, 1), coin.rotation_deg)
    return body.translate((px, py, base_z_mm))


def _coin_overlap_z_range(coin, z_min: float, z_max: float
                          ) -> tuple[float, float] | None:
    """If `[z_min, z_max]` overlaps the coin's z range, return the
    intersection as `(lo, hi)`; else None. Used to size the cutting
    stamp to the actual overlap thickness for each FR4/Cu layer."""
    lo = max(z_min, coin.z_bottom_mm)
    hi = min(z_max, coin.z_top_mm)
    if hi <= lo:
        return None
    return (lo, hi)


def _cut_coin_from_layer(body, coin, *, layer_z_lo: float, layer_z_hi: float,
                          coin_z_lo: float, coin_z_hi: float):
    """If the coin straddles the layer's global Z range, cut its
    chamfered footprint (over the overlap thickness) from `body` at the
    correct global Z. All four Z values are in the same global frame
    (layered-walk frame, not the coin's bend-sim frame). Returns the
    cut body, or the original if there's no overlap."""
    lo = max(layer_z_lo, coin_z_lo)
    hi = min(layer_z_hi, coin_z_hi)
    if hi <= lo:
        return body
    stamp = _coin_extruded_body(coin, thickness_mm=hi - lo, base_z_mm=lo)
    return body.cut(stamp)


@dataclasses.dataclass
class LayerBody:
    """One solid body in the layered assembly, with its solver-facing
    material properties already resolved."""
    name: str                       # `<board>.<role>`
    role: str                       # "copper" | "dielectric" | "metal_backing"
                                     # | "chip" | "encapsulant"
    material: str                   # human-readable material name
    thickness_mm: float
    z_min_mm: float
    z_max_mm: float
    # Mechanical (None if not in catalog).
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    density_kg_m3: float | None = None
    # Electrical / EM (None if not applicable).
    epsilon_r: float | None = None
    loss_tangent: float | None = None
    conductivity_s_m: float | None = None
    # Free-form catch-all the writer surfaces in the JSON manifest.
    note: str | None = None


def _disc_solid(board, thickness_mm: float):
    """A board-shaped disc/rect extruded by `thickness_mm`, with the
    board's NPTH holes drilled through. Base at z=0; caller translates
    the result into its slot in the stack."""
    import cadquery as cq
    g = board.geometry
    if g is not None and g.shape == "circle" and g.diameter_mm:
        wp = cq.Workplane("XY").circle(g.diameter_mm / 2.0).extrude(thickness_mm)
    elif g is not None and g.shape == "rect" and g.rect_dimensions:
        w, h = g.rect_dimensions
        wp = cq.Workplane("XY").rect(w, h).extrude(thickness_mm)
    else:
        raise ValueError(f"board {board.name!r}: unsupported geometry {g}")
    for hole in (getattr(g, "holes", None) or []):
        x, y = hole.position_mm
        wp = (wp.faces(">Z").workplane(centerOption="ProjectedOrigin")
              .moveTo(x, y).hole(hole.diameter_mm))
    return wp


def _copper_foil_props(layer, fab):
    """Pull copper-foil electrical / mechanical constants from the
    FabProfile catalog if available; else fall back to bulk Cu values."""
    if fab is not None:
        for f in fab.foils:
            if f.thickness_um == layer.thickness_um:
                return {
                    "youngs_modulus_gpa": (f.youngs_modulus_gpa
                                            or DEFAULT_COPPER_E_GPA),
                    "poisson_ratio": f.poisson_ratio or DEFAULT_COPPER_NU,
                    "density_kg_m3": f.density_kg_m3 or DEFAULT_COPPER_RHO,
                    "conductivity_s_m": (f.conductivity_s_m
                                          or DEFAULT_COPPER_SIGMA_S_M),
                }
    return {
        "youngs_modulus_gpa": DEFAULT_COPPER_E_GPA,
        "poisson_ratio": DEFAULT_COPPER_NU,
        "density_kg_m3": DEFAULT_COPPER_RHO,
        "conductivity_s_m": DEFAULT_COPPER_SIGMA_S_M,
    }


def _iter_pad_world_geom(board, face: str):
    """Yield `(world_x, world_y, pw, ph, shape, rot_deg, pad)` for every
    pad on the given face — pad's native (un-expanded) size in
    world coordinates after the chip's rotation + bottom-face X-mirror
    convention is applied. The caller decides what to do with the
    geometry (mask opening with expansion, native pad as Cu, etc.)."""
    import math
    cu_face = "F.Cu" if face == "top" else "B.Cu"
    for pl in (board.chip_placements or []):
        if pl.face != face:
            continue
        chip = pl.item
        fp = getattr(chip, "footprint", None)
        if fp is None:
            continue
        chip_x, chip_y = pl.position_mm
        r_deg = pl.rotation_deg or 0.0
        cos_r = math.cos(math.radians(r_deg))
        sin_r = math.sin(math.radians(r_deg))
        for pad in (fp.pads or []):
            if pad.layer not in (cu_face, "*.Cu"):
                continue
            local_x, local_y = pad.position_mm
            if face == "bottom":
                local_x = -local_x
            wx = chip_x + (local_x * cos_r - local_y * sin_r)
            wy = chip_y + (local_x * sin_r + local_y * cos_r)
            pw, ph = pad.size_mm
            yield (wx, wy, float(pw), float(ph), pad.shape, r_deg, pad)


def _pad_solid(wx: float, wy: float, w: float, h: float, shape: str,
                r_deg: float, base_z: float, thickness_mm: float):
    """Build one pad's solid at its world (x, y, base_z) with size (w, h)
    and shape ('round' / 'rect' / 'oval' / 'roundrect' / 'custom').
    The caller is responsible for any pre-applied expansion."""
    import cadquery as cq
    if shape == "round":
        solid = (cq.Workplane("XY", origin=(wx, wy, base_z))
                 .circle(max(w, h) / 2.0)
                 .extrude(thickness_mm))
    else:
        solid = (cq.Workplane("XY", origin=(wx, wy, base_z))
                 .rect(w, h)
                 .extrude(thickness_mm))
        if r_deg:
            solid = solid.rotate(
                (wx, wy, base_z),
                (wx, wy, base_z + 1),
                r_deg,
            )
    return solid


def _track_segment_solid(p1, p2, width_mm: float, base_z: float,
                          thickness_mm: float):
    """Build a rectangle solid for one straight track segment from p1 to
    p2 with the given width and Cu thickness, positioned at z=base_z."""
    import cadquery as cq
    import math
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return None
    mid_x = (p1[0] + p2[0]) / 2.0
    mid_y = (p1[1] + p2[1]) / 2.0
    angle_deg = math.degrees(math.atan2(dy, dx))
    rect = (cq.Workplane("XY", origin=(mid_x, mid_y, base_z))
            .rect(length, width_mm).extrude(thickness_mm))
    if angle_deg:
        rect = rect.rotate((mid_x, mid_y, base_z),
                           (mid_x, mid_y, base_z + 1),
                           angle_deg)
    return rect


def _zone_polygon_solid(outline_mm, base_z: float, thickness_mm: float):
    """Build a polygon solid for one zone outline."""
    import cadquery as cq
    if len(outline_mm) < 3:
        return None
    return (cq.Workplane("XY", origin=(0, 0, base_z))
            .polyline([tuple(p) for p in outline_mm])
            .close()
            .extrude(thickness_mm))


def _cu_pattern_for_layer(board, layer_name: str, base_z: float,
                            thickness_mm: float):
    """Build the etched copper pattern for the named Cu layer as the
    fused union of tracks + zones + pads on that layer.

    Returns `(body, feature_counts_dict)` where `feature_counts_dict`
    has keys `tracks`, `zones`, `pads`. Returns `(None, {…})` with
    all-zero counts when this layer has no routing data — caller falls
    back to a full disc and notes the layer as an unrouted approximation.
    """
    import cadquery as cq
    parts = []
    counts = {"tracks": 0, "zones": 0, "pads": 0}

    for track in (getattr(board, "tracks", None) or []):
        if track.layer != layer_name:
            continue
        for p1, p2 in zip(track.path, track.path[1:]):
            seg = _track_segment_solid(p1, p2, track.width_mm,
                                        base_z, thickness_mm)
            if seg is not None:
                parts.append(seg.val())
                counts["tracks"] += 1

    for zone in (getattr(board, "zones", None) or []):
        if zone.layer != layer_name:
            continue
        z_solid = _zone_polygon_solid(zone.outline_mm, base_z, thickness_mm)
        if z_solid is not None:
            parts.append(z_solid.val())
            counts["zones"] += 1

    # Pads on outer Cu layers — inner layers have no pads.
    if layer_name in ("F.Cu", "B.Cu"):
        face = "top" if layer_name == "F.Cu" else "bottom"
        for wx, wy, w, h, shape, rot, _pad in _iter_pad_world_geom(board, face):
            ps = _pad_solid(wx, wy, w, h, shape, rot, base_z, thickness_mm)
            parts.append(ps.val())
            counts["pads"] += 1

    if not parts:
        return None, counts
    return cq.Workplane(cq.Compound.makeCompound(parts)), counts


def _pad_openings_for_face(board, face: str, base_z: float,
                            thickness_mm: float,
                            expansion_mm: float = DEFAULT_MASK_EXPANSION_MM):
    """Build a SINGLE cadquery body that's the union of every pad's
    soldermask opening on the given face (`"top"` → F.Cu / `"bottom"`
    → B.Cu). Returns `None` if no pads land on this face.

    Each pad's outline is enlarged by its `solder_mask_expansion_mm`
    (or `expansion_mm` if not set) — the typical 50 µm gap that
    prevents mask flowing onto the pad during cure. Pads tagged
    `*.Cu` (PTH) open through both faces.

    BGAs / VFBGAs with 300+ pads use a single compound for the cut
    instead of N×O(boolean) unions, which makes the assembly time
    O(N) instead of O(N²).
    """
    import cadquery as cq

    pad_shapes = []
    for wx, wy, pw, ph, shape, r_deg, pad in _iter_pad_world_geom(board, face):
        exp = pad.solder_mask_expansion_mm
        exp = expansion_mm if exp is None else exp
        ps = _pad_solid(wx, wy, pw + 2.0 * exp, ph + 2.0 * exp,
                        shape, r_deg, base_z, thickness_mm)
        pad_shapes.append(ps.val())

    if not pad_shapes:
        return None
    # Fuse the per-pad solids into one compound — single boolean cut on
    # the mask. cadquery handles `makeCompound` cheaply (it doesn't
    # materialise a fused BREP).
    return cq.Workplane(cq.Compound.makeCompound(pad_shapes))


def _dielectric_props(diel) -> dict:
    """Pull dielectric constants straight off the `Dielectric` instance
    — the stackup fitter already resolved them from the FabProfile."""
    return {
        "youngs_modulus_gpa": diel.youngs_modulus_gpa,
        "poisson_ratio": diel.poisson_ratio,
        "density_kg_m3": diel.density_kg_m3,
        "epsilon_r": diel.epsilon_r,
        "loss_tangent": diel.loss_tangent,
    }


def build_layered_board_assembly(board, *, fab=None, base_z: float = 0.0,
                                  with_components: bool = True,
                                  with_al_backing: bool = True):
    """Walk `board.stackup` and build a per-layer cadquery assembly.

    Returns `(cadquery.Assembly, list[LayerBody])`. Thin wrapper around
    `iter_layered_board_bodies` — calls the iterator and aggregates the
    yielded bodies into one assembly tagged by name. For use cases that
    need the bodies WITHOUT an enclosing assembly (e.g. the folded-
    stack exporter applies a per-tile fold pose to each body before
    aggregating), call `iter_layered_board_bodies` directly.
    """
    import cadquery as cq
    asm = cq.Assembly()
    layer_records: list[LayerBody] = []
    for body, record, color in iter_layered_board_bodies(
            board, fab=fab, base_z=base_z,
            with_components=with_components,
            with_al_backing=with_al_backing):
        asm.add(body, name=record.name, color=color)
        layer_records.append(record)
    return asm, layer_records


def _yield_coin_bodies(board, base_z: float = 0.0):
    """Emit each `Board.cu_coin_inserts` entry as a Cu prism. Called by
    `iter_layered_board_bodies` AFTER the stackup walk (so the coins
    are added last). Each coin's footprint has already been cut out of
    the overlapping FR4 / Cu layers, so the coin slots in cleanly
    without overlap. `base_z` shifts the whole emission so the coin's
    z range tracks the board's base — by default coins are anchored to
    B.Cu bottom = 0; if the board's stack starts higher (Al backing,
    bottom soldermask), the caller passes the offset."""
    import cadquery as cq
    coins = getattr(board, "cu_coin_inserts", None) or []
    if not coins:
        return
    for i, coin in enumerate(coins):
        body = _coin_extruded_body(
            coin, thickness_mm=coin.thickness_mm,
            base_z_mm=base_z + coin.z_bottom_mm,
        )
        # NCAB Copper Coin Design Guide 1.0 — body material is
        # electrolytic Cu (same alloy as the foil layers).
        name = (f"{board.name}.cu_coin_{i}_"
                f"{coin.kind}{int(round(coin.length_mm))}x"
                f"{int(round(coin.width_mm))}")
        z_lo = base_z + coin.z_bottom_mm
        z_hi = z_lo + coin.thickness_mm
        yield (body, LayerBody(
            name=name, role="cu_coin", material="copper",
            thickness_mm=coin.thickness_mm,
            z_min_mm=z_lo, z_max_mm=z_hi,
            youngs_modulus_gpa=DEFAULT_COPPER_E_GPA,
            poisson_ratio=DEFAULT_COPPER_NU,
            density_kg_m3=DEFAULT_COPPER_RHO,
            conductivity_s_m=DEFAULT_COPPER_SIGMA_S_M,
            note=(f"NCAB Cu coin {coin.kind}, "
                  f"{coin.length_mm:.1f}×{coin.width_mm:.1f}×"
                  f"{coin.thickness_mm:.1f} mm "
                  f"(ladder {coin.ladder_length_mm:.1f}×"
                  f"{coin.ladder_width_mm:.1f}, "
                  f"R={coin.corner_chamfer_radius_mm:.1f} mm chamfer); "
                  f"low-Z F.Cu→B.Cu shortcut for EM, "
                  f"structural-coin in the bend sim. "
                  f"{coin.note or ''}".strip()),
        ), cq.Color(0.85, 0.55, 0.20, 1.0))


def iter_layered_board_bodies(board, *, fab=None, base_z: float = 0.0,
                                with_components: bool = True,
                                with_al_backing: bool = True):
    """Yield `(body, LayerBody, color)` triples for each layer of `board`.

    Internal builder shared between `build_layered_board_assembly` and
    the folded-stack exporter — yielding tuples (rather than adding to
    an assembly directly) lets the folded walk apply a per-tile fold
    pose to each body before aggregating.

    The bottom of the physical board sits at `z = base_z`; the FR4 + Cu
    stack grows upward. An optional Al backing is added BELOW the
    stack (matching the bend-sim's composite-D walk). Per-chip
    component blocks ride on F.Cu / B.Cu when `with_components`."""
    import cadquery as cq

    z = base_z
    stackup = list(board.stackup or [])
    if not stackup:
        raise ValueError(f"{board.name!r}: empty stackup — fit one first "
                         "(`board.set_fitted_stackup()`)")

    mask_total_mm = (getattr(board, "MASK_FINISH_MM", 0.0) or 0.0)
    mask_per_side_mm = mask_total_mm / 2.0 if mask_total_mm > 0 else 0.0

    # Coin Z anchor — coin.z_bottom_mm is referenced to B.Cu bottom = 0
    # in the bend sim, which corresponds to the cumulative `z` just
    # AFTER the Al backing + bottom soldermask in the layered walk.
    # Compute that offset once so coin overlaps and the final
    # `_yield_coin_bodies` call land at the same physical Z.
    al_mm = (getattr(board, "al_backing_mm", 0.0) or 0.0) if with_al_backing else 0.0
    coin_z_anchor = z + al_mm
    if mask_per_side_mm > 0:
        coin_z_anchor += mask_per_side_mm
    coins = getattr(board, "cu_coin_inserts", None) or []

    # ── optional Al backing below B.Cu ─────────────────────────────────
    if al_mm > 0:
        body = _disc_solid(board, al_mm).translate((0, 0, z))
        name = f"{board.name}.al_backing"
        yield (body, LayerBody(
            name=name, role="metal_backing", material="aluminium",
            thickness_mm=al_mm, z_min_mm=z, z_max_mm=z + al_mm,
            youngs_modulus_gpa=70.0, poisson_ratio=0.33,
            density_kg_m3=2700.0, conductivity_s_m=3.5e7,
            note="6061-T6 thermal/structural backing",
        ), cq.Color(0.6, 0.6, 0.65, 1.0))
        z += al_mm

    # ── bottom soldermask (below B.Cu, between B.Cu and the world or
    #    Al backing). LPSM is a permanent epoxy coating on the outer
    #    Cu surfaces — matters for mmWave EM surface impedance. The
    #    openings over each B.Cu pad are cut out so the mesh sees
    #    bare-Cu wettable regions; mmWave traces above pad regions
    #    have AIR rather than epoxy as their immediate dielectric. ─
    if mask_per_side_mm > 0:
        mask_body = _disc_solid(board, mask_per_side_mm).translate((0, 0, z))
        openings = _pad_openings_for_face(board, "bottom", z,
                                           mask_per_side_mm)
        n_openings_bot = 0
        if openings is not None:
            mask_body = mask_body.cut(openings)
            n_openings_bot = len(openings.val().Solids())
        name = f"{board.name}.soldermask_bottom"
        yield (mask_body, LayerBody(
            name=name, role="soldermask", material="LPSM",
            thickness_mm=mask_per_side_mm,
            z_min_mm=z, z_max_mm=z + mask_per_side_mm,
            youngs_modulus_gpa=SOLDERMASK_E_GPA,
            poisson_ratio=SOLDERMASK_NU,
            density_kg_m3=SOLDERMASK_RHO,
            epsilon_r=SOLDERMASK_EPSILON_R,
            loss_tangent=SOLDERMASK_LOSS_TANGENT,
            note=(f"bottom LPSM finish (Taiyo / Peters-class epoxy); "
                  f"ε_r and tan δ are catalog defaults — verify "
                  f"against the actual fab's data sheet. "
                  f"{n_openings_bot} pad openings cut."),
        ), cq.Color(0.1, 0.3, 0.15, 1.0))
        z += mask_per_side_mm

    # ── stackup walk — bottom-up (B.Cu first, F.Cu last) ───────────────
    # `board.stackup` is top-to-bottom (F.Cu first); reverse to walk up.
    # Track each layer's (z_min, z_max) in `cu_z` so via barrels can
    # later resolve from_layer / to_layer → barrel extent.
    cu_z: dict = {}
    for i in range(len(stackup) - 1, -1, -1):
        upper = stackup[i - 1] if i > 0 else None
        layer = stackup[i]
        t_cu_mm = layer.thickness_um / 1000.0
        # Copper pattern OR full-disc fallback. If the board has any
        # routing data (tracks / zones / pads on this layer), emit the
        # etched pattern as the union of those features. If the layer
        # is unrouted, fall back to a full disc and mark it in the
        # note so a solver knows to treat it as approximate.
        cu_pattern, feats = _cu_pattern_for_layer(
            board, layer.name, z, t_cu_mm)
        if cu_pattern is not None:
            body = cu_pattern
            cu_note = (f"etched pattern: {feats['tracks']} track segments + "
                       f"{feats['zones']} zones + {feats['pads']} pads")
        else:
            body = _disc_solid(board, t_cu_mm).translate((0, 0, z))
            cu_note = ("unrouted: full plane approximation — overestimates "
                       "Cu coverage; treat as conservative shielding model")
        # Subtract any coin that straddles this Cu foil's Z range — the
        # coin's Cu body emitted at the end replaces what we cut.
        for coin in coins:
            body = _cut_coin_from_layer(
                body, coin,
                layer_z_lo=z, layer_z_hi=z + t_cu_mm,
                coin_z_lo=coin_z_anchor + coin.z_bottom_mm,
                coin_z_hi=coin_z_anchor + coin.z_top_mm,
            )
        name = f"{board.name}.{layer.name}"
        cu_props = _copper_foil_props(layer, fab)
        yield (body, LayerBody(
            name=name, role="copper", material="copper",
            thickness_mm=t_cu_mm,
            z_min_mm=z, z_max_mm=z + t_cu_mm,
            note=cu_note,
            **cu_props,
        ), cq.Color(0.7, 0.45, 0.1, 1.0))
        cu_z[layer.name] = (z, z + t_cu_mm)
        z += t_cu_mm
        # Dielectric ABOVE this layer (between layer[i] and layer[i-1]).
        # In `Layer.dielectric_below` semantics: the upper layer's
        # `dielectric_below` is what sits BELOW it, i.e. between layer
        # i-1 (upper) and layer i (lower). So when walking up, the
        # dielectric we want is `upper.dielectric_below` if upper exists.
        if upper is not None:
            diel = upper.dielectric_below
            if diel is not None:
                t_d_mm = diel.thickness_um / 1000.0
                body = _disc_solid(board, t_d_mm).translate((0, 0, z))
                # Same coin subtraction as for Cu foils — the coin's
                # bulk Cu replaces FR4 wherever the two overlap.
                for coin in coins:
                    body = _cut_coin_from_layer(
                        body, coin,
                        layer_z_lo=z, layer_z_hi=z + t_d_mm,
                        coin_z_lo=coin_z_anchor + coin.z_bottom_mm,
                        coin_z_hi=coin_z_anchor + coin.z_top_mm,
                    )
                name = f"{board.name}.dielectric_below_{upper.name}"
                yield (body, LayerBody(
                    name=name, role="dielectric",
                    material=diel.material,
                    thickness_mm=t_d_mm,
                    z_min_mm=z, z_max_mm=z + t_d_mm,
                    **_dielectric_props(diel),
                    note=diel.note,
                ), cq.Color(0.4, 0.6, 0.4, 1.0))
                z += t_d_mm

    # ── top soldermask (above F.Cu, between F.Cu and the world or
    #    chip bodies). Same LPSM material as the bottom mask. Openings
    #    over each F.Cu pad let the mmWave traces on F.Cu see AIR
    #    directly above their conductor — the key dielectric variation
    #    that drives the radar SIW launch's effective permittivity. ─
    if mask_per_side_mm > 0:
        mask_body = _disc_solid(board, mask_per_side_mm).translate((0, 0, z))
        openings = _pad_openings_for_face(board, "top", z, mask_per_side_mm)
        n_openings_top = 0
        if openings is not None:
            mask_body = mask_body.cut(openings)
            n_openings_top = len(openings.val().Solids())
        name = f"{board.name}.soldermask_top"
        yield (mask_body, LayerBody(
            name=name, role="soldermask", material="LPSM",
            thickness_mm=mask_per_side_mm,
            z_min_mm=z, z_max_mm=z + mask_per_side_mm,
            youngs_modulus_gpa=SOLDERMASK_E_GPA,
            poisson_ratio=SOLDERMASK_NU,
            density_kg_m3=SOLDERMASK_RHO,
            epsilon_r=SOLDERMASK_EPSILON_R,
            loss_tangent=SOLDERMASK_LOSS_TANGENT,
            note=(f"top LPSM finish; mmWave traces on F.Cu see this "
                  f"as their immediate dielectric environment. "
                  f"{n_openings_top} pad openings cut."),
        ), cq.Color(0.1, 0.3, 0.15, 1.0))
        z += mask_per_side_mm

    z_top = z

    # ── Cu coin inserts — emit each coin as its own Cu prism at the
    #    z range already cut out of the FR4 / Cu layers above. Coin Z
    #    in CuCoinInsert is anchored to B.Cu bottom = 0; the layered-
    #    walk anchor is `coin_z_anchor` (Al backing + bottom mask
    #    above base_z). Yielding here keeps the coin colour visible in
    #    the assembly tree alongside its host layers.
    for body_and_record in _yield_coin_bodies(board, base_z=coin_z_anchor):
        yield body_and_record

    # ── via barrels — solid Cu cylinders spanning from_layer to
    #    to_layer for each entry in board.vias. EM at GHz sees a
    #    fully-plated barrel as a solid conductor (skin depth ≪
    #    plating thickness); the solid-Cu approximation is exact for
    #    f > 1 GHz and a small over-estimate of mass for mechanical /
    #    thermal at f → 0 (open vias have a small inner void).
    vias = getattr(board, "vias", None) or []
    for k, via in enumerate(vias):
        z_lo = cu_z.get(via.to_layer)
        z_hi = cu_z.get(via.from_layer)
        if z_lo is None or z_hi is None:
            continue
        bottom_z = min(z_lo[0], z_hi[0])
        top_z = max(z_lo[1], z_hi[1])
        barrel_h = top_z - bottom_z
        if barrel_h <= 0 or via.drill_mm <= 0:
            continue
        x, y = via.position_mm
        cyl = (cq.Workplane("XY", origin=(x, y, bottom_z))
               .circle(via.drill_mm / 2.0)
               .extrude(barrel_h))
        name = f"{board.name}.via.{k}.{via.from_layer}_to_{via.to_layer}"
        yield (cyl, LayerBody(
            name=name, role="via_barrel", material="copper",
            thickness_mm=barrel_h,
            z_min_mm=bottom_z, z_max_mm=top_z,
            youngs_modulus_gpa=DEFAULT_COPPER_E_GPA,
            poisson_ratio=DEFAULT_COPPER_NU,
            density_kg_m3=DEFAULT_COPPER_RHO,
            conductivity_s_m=DEFAULT_COPPER_SIGMA_S_M,
            note=(f"{via.kind} via, drill Ø{via.drill_mm} mm, "
                  f"net {via.net or 'unbound'}; modelled as solid Cu"
                  + (" (filled)" if via.filled else "")),
        ), cq.Color(0.85, 0.6, 0.15, 1.0))

    # ── chip blocks on top / bottom face ───────────────────────────────
    if with_components:
        for pl in (board.chip_placements or []):
            c = pl.item
            if not isinstance(c, (Chip, Antenna)):
                continue
            fp = getattr(c, "footprint", None)
            if fp is None:
                continue
            lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(fp)
            w, h = hi_x - lo_x, hi_y - lo_y
            if w <= 0 or h <= 0:
                w, h = getattr(fp, "size_mm", None) or (1.0, 1.0)
            ht = (getattr(fp, "height_mm", None)
                  or getattr(c, "height_mm", None) or 0.5)
            if w <= 0 or h <= 0 or ht <= 0:
                continue
            x, y = pl.position_mm
            face = getattr(pl, "face", "top") or "top"
            base_chip_z = z_top if face == "top" else (base_z + (al_mm if al_mm > 0 else 0.0)) - ht
            blk = (
                __import__("cadquery").Workplane("XY")
                .box(w, h, ht, centered=(True, True, False))
                .rotate((0, 0, 0), (0, 0, 1),
                        getattr(pl, "rotation_deg", 0.0) or 0.0)
                .translate((x, y, base_chip_z))
            )
            name = f"{board.name}.chip.{c.ref}"
            # Silicon die mechanical defaults — passed through `Chip`
            # if populated, else generic Si values.
            E_si = getattr(c, "youngs_modulus_gpa", None) or 130.0
            cte_si = getattr(c, "cte_ppm_k", None)
            yield (blk, LayerBody(
                name=name, role="chip", material="silicon_pkg",
                thickness_mm=ht,
                z_min_mm=base_chip_z, z_max_mm=base_chip_z + ht,
                youngs_modulus_gpa=E_si, poisson_ratio=0.28,
                density_kg_m3=2330.0,
                note=(f"ref {c.ref}; CTE {cte_si} ppm/K"
                       if cte_si else f"ref {c.ref}"),
            ), cq.Color(0.8, 0.75, 0.2, 1.0))


def write_layered_board_step(board, output_path: str | pathlib.Path,
                              *, fab=None,
                              with_components: bool = True,
                              with_al_backing: bool = True) -> dict:
    """Write `<output_path>.step` + sibling `.json` manifest.

    `output_path` may include the `.step` suffix or not — the JSON
    sidecar always lands at the same stem with `.json`.

    Returns a summary dict with body counts + the manifest path. Raises
    ImportError if cadquery isn't installed.
    """
    import cadquery as cq                             # noqa: F401

    asm, layers = build_layered_board_assembly(
        board, fab=fab,
        with_components=with_components,
        with_al_backing=with_al_backing,
    )

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() != ".step":
        out = out.with_suffix(".step")
    cq.exporters.assembly.exportAssembly(asm, str(out), "STEP")

    # JSON manifest — body name → material properties. Total extent is
    # the assembly's Z bounding box (chip blocks can stick out above /
    # below the stack so `layers[-1]` is not necessarily the topmost
    # body).
    if layers:
        z_lo = min(l.z_min_mm for l in layers)
        z_hi = max(l.z_max_mm for l in layers)
        stack_extent_mm = z_hi - z_lo
    else:
        stack_extent_mm = 0.0
    manifest = {
        "board": board.name,
        "thickness_mm": stack_extent_mm,
        "layer_count": len(layers),
        "bodies": [dataclasses.asdict(l) for l in layers],
    }
    json_out = out.with_suffix(".json")
    json_out.write_text(json.dumps(manifest, indent=2))

    return {
        "output_step_path": str(out),
        "output_json_path": str(json_out),
        "n_bodies": len(layers),
        "n_copper": sum(1 for l in layers if l.role == "copper"),
        "n_dielectric": sum(1 for l in layers if l.role == "dielectric"),
        "n_chip": sum(1 for l in layers if l.role == "chip"),
        "n_metal": sum(1 for l in layers if l.role == "metal_backing"),
        "n_soldermask": sum(1 for l in layers if l.role == "soldermask"),
        "n_via_barrel": sum(1 for l in layers if l.role == "via_barrel"),
        "n_cu_coin": sum(1 for l in layers if l.role == "cu_coin"),
        "thickness_mm": manifest["thickness_mm"],
    }


def write_all_layered_steps(boards: dict, output_dir: str | pathlib.Path,
                             *, fab=None,
                             with_components: bool = True,
                             with_al_backing: bool = True) -> list[dict]:
    """Write a layered STEP per rigid tile in `boards` to `output_dir`.

    Skips spacers (they're handled by `spacer_step.write_spacer_step`)
    and flex tiles (those are polyimide carriers without a fab
    stackup). Returns the list of summary dicts from
    `write_layered_board_step`.
    """
    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear stale layered files — same idempotency story as the other
    # exporters in this package.
    for pattern in ("*_layered.step", "*_layered.json"):
        for old in out_dir.glob(pattern):
            old.unlink()
    results = []
    for name, b in boards.items():
        if getattr(b, "is_spacer", False):
            continue
        if getattr(b, "kind", "rigid") != "rigid":
            continue
        if not (b.stackup or []):
            continue
        r = write_layered_board_step(
            b, out_dir / f"{name}_layered.step", fab=fab,
            with_components=with_components,
            with_al_backing=with_al_backing,
        )
        results.append(r)
    return results
