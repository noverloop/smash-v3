"""WR-10 waveguide throat stubs over the AWR2E44P launches.

First step of the nose-cap waveguide/horn block: eight rectangular WR-10
throat stubs standing vertically (+Z) on the launch plane of the
AWR2E44P, each centred on one of the chip's on-package waveguide launches
(TX1-4 / RX1-4) and oriented to match the footprint marker. Pure
cadquery; this step only POSITIONS the rectangles — no bends, elevation
tilts or horns yet — so we can eyeball that they land exactly over the
chip's RF ports relative to the BGA ball grid. The radiation tilts
(TX +30deg, RX +15/+45deg) and the pyramidal horns from
waveguide/waveguide_radiator_design.md come later.

Launch positions + orientations are read live from the AWR2E44P
footprint's Dwgs.User layer (the single source of truth — its launch
extents carry a "needs datasheet reconciliation" note, so reading them
keeps this in sync). The cross-section is WR-10 (2.54 x 1.27 mm).

The launch *markers* are ~1.95 x 1.30 mm — SMALLER than WR-10, so they
are not the guide cross-section "including walls" (walls would only make
the envelope larger). They are the on-package launch / coupling aperture
(narrow dim ~= WR-10 b = 1.27, broad dim pinched in): the WR-10 throat
mates over this aperture, it is not a 1:1 match. The stub stays WR-10;
the marker is rendered separately so the relationship is visible.

Frames. The smash model is math y-up; `_artifacts` negates KiCad's
y-down on import, so a launch label at KiCad (xk, yk) is footprint-local
(xk, -yk). The chip's resolved placement (position_mm, rotation_deg)
maps a footprint-local point into the radar-board frame as
`Rz(theta)*p + (cx, cy)`. radar -> nose_cap is an identity fold (two
mirror_x, no net mirror — see `_mark_radar_block_cutout`), so the same
(x, y) holds in the nose_cap-local frame where the waveguide block
mounts:

    launch_nose = Rz(theta) . (xk, -yk) + (cx, cy)        # no mirror

Verification context. There is NO PCB between the launches and the
stubs: the chip top IS the launch plane (z=0), the WR-10 stubs sit on it
across a small choke air gap, and the AWR package body + its BGA balls +
an optional plain verification PCB stack DOWNWARD from z=0. So the export
shows the WR-10 stubs directly above the BGA ball grid for alignment.
"""
from __future__ import annotations

import dataclasses
import math
import pathlib
import re

from smash.parts._artifacts import (
    src, fp_lines_on_layer, pads_from_kicad_mod, _read_text)


# ── WR-10 + stub geometry constants ─────────────────────────────────────
WR10_LONG_MM = 2.54            # broad wall (E-plane long dimension)
WR10_SHORT_MM = 1.27           # narrow wall
DEFAULT_STUB_LENGTH_MM = 3.0   # design doc "short run ~3 mm" before the bend
DEFAULT_COUPLING_GAP_MM = 0.1  # chip top <-> WR-10 throat (choke flange air gap)
LAUNCH_LAYER = "Dwgs.User"
AWR_FOOTPRINT_NAME = "AWR2E44PBGAMXRQ1"
AWR_SIZE_MM = (13.5, 12.0)     # AWR2E44P FCCSP package body
AWR_HEIGHT_MM = 1.234          # datasheet AMX outline, 1.234 mm MAX

# fp_text user "<TXn|RXn>" (at x y ...) — capture the label + its centre.
# The hidden "-- waveguide launches --" header has no TX/RX name, so it is
# skipped. `at` may carry a 3rd rotation field; we only need x/y.
_LAUNCH_TEXT_RX = re.compile(
    r'\(fp_text\s+user\s+"(?P<name>(?:TX|RX)\d)"\s+\(at\s+'
    r'(?P<x>-?\d+(?:\.\d+)?)\s+(?P<y>-?\d+(?:\.\d+)?)')


@dataclasses.dataclass(frozen=True)
class Launch:
    """One on-package waveguide launch: name, centre in the chip
    footprint-local (math y-up) frame, the marker rectangle size (the
    coupling aperture, ~1.95 x 1.30 mm — NOT the WR-10 channel), and the
    long axis ("x"/"y") the WR-10 broad wall aligns to."""
    name: str
    center_mm: tuple
    size_mm: tuple
    long_axis: str


def extract_launches(kicad_mod_path: str | None = None,
                     *, layer: str = LAUNCH_LAYER) -> list[Launch]:
    """The 8 TX/RX waveguide launches from the AWR2E44P footprint.

    Centres come from the `fp_text` labels (authoritative); the marker
    rectangle bbox gives the aperture size and long axis. All in the smash
    footprint-local (math y-up) frame. Raises if the footprint does not
    yield exactly 8 launches, or if any label centre disagrees with its
    rectangle centre (a desynced marker).
    """
    path = kicad_mod_path or src(AWR_FOOTPRINT_NAME, f"{AWR_FOOTPRINT_NAME}.kicad_mod")
    text = _read_text(path)

    # Launch centres from the labels. KiCad is y-down → negate to y-up.
    centers = {m.group("name"): (float(m.group("x")), -float(m.group("y")))
               for m in _LAUNCH_TEXT_RX.finditer(text)}
    if len(centers) != 8:
        raise ValueError(
            f"{AWR_FOOTPRINT_NAME}: expected 8 launch labels on {layer}, "
            f"found {sorted(centers)}")

    # Marker rectangles (already y-negated by fp_lines_on_layer) give the size
    # + long axis. Assign each segment to its nearest launch centre and
    # accumulate the endpoint bbox. Launch centres are >2.5 mm apart and a
    # rectangle edge midpoint is <1 mm from its own centre, so the nearest
    # centre is unambiguous.
    INF = float("inf")
    bbox = {n: [INF, INF, -INF, -INF] for n in centers}
    for (a, b) in fp_lines_on_layer(path, layer):
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        n = min(centers, key=lambda k: (centers[k][0] - mx) ** 2
                + (centers[k][1] - my) ** 2)
        bb = bbox[n]
        for (px, py) in (a, b):
            bb[0], bb[1] = min(bb[0], px), min(bb[1], py)
            bb[2], bb[3] = max(bb[2], px), max(bb[3], py)

    launches: list[Launch] = []
    for name, c in centers.items():
        x0, y0, x1, y1 = bbox[name]
        if not math.isfinite(x0):
            raise ValueError(f"{AWR_FOOTPRINT_NAME}: no {layer} rectangle for {name}")
        bx, by = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        if abs(bx - c[0]) > 1e-3 or abs(by - c[1]) > 1e-3:
            raise ValueError(
                f"{AWR_FOOTPRINT_NAME}: {name} label {c} != rect centre "
                f"({bx:.3f},{by:.3f}) — marker desynced")
        w, h = x1 - x0, y1 - y0
        launches.append(Launch(name=name, center_mm=c, size_mm=(w, h),
                               long_axis=("x" if w >= h else "y")))

    launches.sort(key=lambda L: (L.name[:2], int(L.name[2:])))  # TX1..TX4, RX1..RX4
    return launches


def _place_xy_fn(placement_position_mm, placement_rotation_deg):
    """A `(px, py) -> (x, y)` mapper applying `Rz(theta) . p + (cx, cy)`."""
    cx, cy = placement_position_mm
    th = math.radians(placement_rotation_deg)
    cos_t, sin_t = math.cos(th), math.sin(th)
    return lambda px, py: (cos_t * px - sin_t * py + cx,
                           sin_t * px + cos_t * py + cy)


def _stub_solids(launches, *, placement_position_mm, placement_rotation_deg,
                 stub_length_mm, long_mm, short_mm, base_z_mm=0.0):
    """`([(name, workplane)], {name: (x, y)})` — one WR-10 stub solid per
    launch in the nose_cap-local frame, plus their placed centres. The
    cross-section is `long_mm` along the launch's long axis, `short_mm`
    across; the broad wall therefore matches the footprint marker. Stubs
    extrude from z=`base_z_mm` up by `stub_length_mm`."""
    import cadquery as cq

    place = _place_xy_fn(placement_position_mm, placement_rotation_deg)
    solids = []
    centers = {}
    for L in launches:
        x, y = place(*L.center_mm)
        base_deg = 0.0 if L.long_axis == "x" else 90.0
        stub = (cq.Workplane("XY")
                .rect(long_mm, short_mm)            # long axis along +X pre-rotate
                .extrude(stub_length_mm)            # +Z = outer/nose
                .rotate((0, 0, 0), (0, 0, 1), base_deg + placement_rotation_deg)
                .translate((x, y, base_z_mm)))
        solids.append((L.name, stub))
        centers[L.name] = (round(x, 4), round(y, 4))
    return solids, centers


def build_waveguide_stub_assembly(
    launches,
    *,
    placement_position_mm=(0.0, 0.0),
    placement_rotation_deg=0.0,
    stub_length_mm=DEFAULT_STUB_LENGTH_MM,
    long_mm=WR10_LONG_MM,
    short_mm=WR10_SHORT_MM,
    coupling_gap_mm=DEFAULT_COUPLING_GAP_MM,
    with_awr_body=True,
    with_awr_balls=True,
    with_launch_markers=True,
    with_pcb=True,
    kicad_mod_path=None,
    awr_size_mm=AWR_SIZE_MM,
    awr_height_mm=AWR_HEIGHT_MM,
    ball_height_mm=0.25,
    pcb_thickness_mm=1.0,
    pcb_margin_mm=3.0,
):
    """Build the 8 WR-10 throat stubs as a `cq.Assembly`, with the AWR2E44P
    chip context stacked DOWNWARD from the launch plane (z=0) so the
    alignment is checkable against the BGA ball grid — there is NO board
    between the launches and the stubs. Layers (top → bottom):

      stubs        z in [gap, gap+length]   WR-10 2.54 x 1.27 (brass)
      launch aper. z in [0, gap]            ~1.95 x 1.30 marker (cyan)
      AWR body     z in [-h, 0]             package, translucent
      BGA balls    z in [-h-ball, -h]       footprint F.Cu pads (copper)
      verify PCB   below the balls          plain board carrying the fp

    Returns `(assembly, {name: (x, y)})`. Raises ImportError without
    cadquery."""
    import cadquery as cq

    asm = cq.Assembly()
    cx, cy = placement_position_mm
    place = _place_xy_fn(placement_position_mm, placement_rotation_deg)

    # AWR package body — top face at z=0 (the launch plane), extends DOWN.
    # Translucent so the balls beneath show through.
    if with_awr_body:
        aw, ah = awr_size_mm
        body = (cq.Workplane("XY")
                .box(aw, ah, awr_height_mm, centered=(True, True, False))
                .rotate((0, 0, 0), (0, 0, 1), placement_rotation_deg)
                .translate((cx, cy, -awr_height_mm)))
        asm.add(body, name="U_AWR", color=cq.Color(0.30, 0.30, 0.35, 0.35))

    # BGA balls — the footprint's F.Cu pads on the package underside. All
    # share Ø0.3, so one fused `pushPoints` solid keeps the STEP small.
    ball_top = -awr_height_mm
    if with_awr_balls:
        path = kicad_mod_path or src(AWR_FOOTPRINT_NAME, f"{AWR_FOOTPRINT_NAME}.kicad_mod")
        circ = [(p.position_mm, p.size_mm[0] / 2.0)
                for p in pads_from_kicad_mod(path) if p.shape == "circle"]
        if circ:
            r0 = circ[0][1]
            uni = [place(px, py) for (px, py), r in circ if abs(r - r0) < 1e-6]
            balls = (cq.Workplane("XY").pushPoints(uni).circle(r0)
                     .extrude(-ball_height_mm).translate((0, 0, ball_top)))
            asm.add(balls, name="awr_bga_balls",
                    color=cq.Color(0.80, 0.55, 0.20, 1.0))
            for (px, py), r in circ:        # any odd-sized pad → its own cyl
                if abs(r - r0) >= 1e-6:
                    x, y = place(px, py)
                    b = (cq.Workplane("XY").circle(r).extrude(-ball_height_mm)
                         .translate((x, y, ball_top)))
                    asm.add(b, name="awr_bga_ball",
                            color=cq.Color(0.80, 0.55, 0.20, 1.0))

    # Plain verification PCB under the balls — the "plain pcb with the AWR
    # footprint" reference plane (a simple rect a margin larger than the chip).
    if with_pcb:
        aw, ah = awr_size_mm
        pcb = (cq.Workplane("XY")
               .rect(aw + 2 * pcb_margin_mm, ah + 2 * pcb_margin_mm)
               .extrude(-pcb_thickness_mm)
               .rotate((0, 0, 0), (0, 0, 1), placement_rotation_deg)
               .translate((cx, cy, ball_top - ball_height_mm)))
        asm.add(pcb, name="verify_pcb", color=cq.Color(0.10, 0.45, 0.20, 0.6))

    # Launch apertures — the actual ~1.95 x 1.30 markers, filling the choke
    # gap [0, gap] under each WR-10 stub so the stub-vs-aperture size
    # relationship is visible. Marker is axis-aligned (w,h) in footprint
    # frame, so only the placement rotation applies.
    if with_launch_markers and coupling_gap_mm > 0:
        for L in launches:
            w, h = L.size_mm
            x, y = place(*L.center_mm)
            mark = (cq.Workplane("XY").rect(w, h).extrude(coupling_gap_mm)
                    .rotate((0, 0, 0), (0, 0, 1), placement_rotation_deg)
                    .translate((x, y, 0.0)))
            asm.add(mark, name=f"launch_{L.name}",
                    color=cq.Color(0.20, 0.70, 0.80, 0.7))

    # The 8 WR-10 stubs — base at the launch plane + coupling gap, up +Z.
    solids, centers = _stub_solids(
        launches, placement_position_mm=placement_position_mm,
        placement_rotation_deg=placement_rotation_deg,
        stub_length_mm=stub_length_mm, long_mm=long_mm, short_mm=short_mm,
        base_z_mm=coupling_gap_mm)
    for name, stub in solids:
        asm.add(stub, name=f"stub_{name}", color=cq.Color(0.85, 0.65, 0.10, 1.0))
    return asm, centers


def write_waveguide_step(
    output_path,
    *,
    placement_position_mm=(0.0, 0.0),
    placement_rotation_deg=0.0,
    kicad_mod_path: str | None = None,
    stub_length_mm: float = DEFAULT_STUB_LENGTH_MM,
    coupling_gap_mm: float = DEFAULT_COUPLING_GAP_MM,
    with_awr_body: bool = True,
    with_awr_balls: bool = True,
    with_launch_markers: bool = True,
    with_pcb: bool = True,
    also_stl: bool = False,
) -> dict:
    """Extract the launches, build the stub + AWR-footprint context assembly
    and export a STEP.

    Returns a summary dict::

        {output_path, n_stubs, stub_length_mm, coupling_gap_mm,
         stub_centers_mm{name:(x,y)}}

    `stub_centers_mm` lets callers/tests assert the transform numerically
    (for an identity placement each centre equals the footprint label's
    (xk, -yk)). With `also_stl=True` the fused stub solids (context dropped)
    are also written as a sibling `.stl`. Raises ImportError without
    cadquery.
    """
    launches = extract_launches(kicad_mod_path)
    asm, centers = build_waveguide_stub_assembly(
        launches,
        placement_position_mm=placement_position_mm,
        placement_rotation_deg=placement_rotation_deg,
        stub_length_mm=stub_length_mm,
        coupling_gap_mm=coupling_gap_mm,
        with_awr_body=with_awr_body,
        with_awr_balls=with_awr_balls,
        with_launch_markers=with_launch_markers,
        with_pcb=with_pcb,
        kicad_mod_path=kicad_mod_path,
    )

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(asm, "export"):                # non-deprecated STEP writer
        asm.export(str(out))
    else:                                     # older cadquery
        asm.save(str(out))

    summary = {
        "output_path": str(out),
        "n_stubs": len(launches),
        "stub_length_mm": stub_length_mm,
        "coupling_gap_mm": coupling_gap_mm,
        "stub_centers_mm": centers,
    }

    if also_stl:
        solids, _ = _stub_solids(
            launches, placement_position_mm=placement_position_mm,
            placement_rotation_deg=placement_rotation_deg,
            stub_length_mm=stub_length_mm,
            long_mm=WR10_LONG_MM, short_mm=WR10_SHORT_MM,
            base_z_mm=coupling_gap_mm)
        fused = None
        for _name, stub in solids:
            fused = stub if fused is None else fused.union(stub)
        if fused is not None:
            from smash.export.stl import write_stl_from_body
            r = write_stl_from_body(fused, out.with_suffix(".stl"))
            summary["stl_path"] = r["output_path"]

    return summary
