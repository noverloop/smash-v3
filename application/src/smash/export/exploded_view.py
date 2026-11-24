"""IKEA-style exploded assembly view along the two stacking pins (2026-11-23).

Nose up, in assembly order: base with pin 2 → aft cap → aft_end_board →
floor plate → battery holder → cells → activation_interface → ring → … →
payload tile → sleeve → nose cap, every part lifted apart along the stack
axis and threaded on pin 1 (Ø2.9, potting holes, r 13 / 135°) and pin 2
(Ø0.99, rim notch, r 16.5 / 285°). Boards are drawn as plain Ø34 discs with
their rim notch and potting hole (orientation view, not a part drawing);
rings, holder, floor plate, aft cap, sleeve and nose cap are their real
STEPs. Each part carries its step number as 3D text; the page lists them.

write_exploded_view(cfg, out_pdf, html_to_pdf) → number of parts drawn.
"""
from __future__ import annotations

import html
import math
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[4]
DIST = REPO / "dist"
MAXI = DIST / "maximalist"
GAP_MM = 9.0                     # explode distance between consecutive parts
# (2026-11-23, user) colours: green PCB, grey metal, yellow PEEK
PCB = (0.16, 0.52, 0.25)
METAL = (0.74, 0.75, 0.77)
METAL_DARK = (0.52, 0.53, 0.56)
PEEK_C = (0.93, 0.80, 0.38)
ZIRCONIA = (0.97, 0.97, 0.95)
LDS_BLACK = (0.60, 0.60, 0.65)     # LDS-grade PEEK (black in reality; dark grey so edges read)
COPPER = (0.85, 0.52, 0.28)
BASE_C = (0.86, 0.86, 0.86)
BOARD_T = 0.868

PAYLOAD = {"core_radar": "radar_module", "core_qpd": "qpd_module", "core_camera": "camera_module"}


def _board_disc(cq):
    from smash.layout import cavities as CAV
    b = cq.Workplane("XY").circle(17.0).extrude(BOARD_T)
    a = math.radians(CAV.ALIGN_NOTCH_ANGLE_DEG)
    L = CAV.ALIGN_NOTCH_DEPTH_MM + 1.0
    rc = 17.0 - CAV.ALIGN_NOTCH_DEPTH_MM + L / 2
    b = b.cut(cq.Workplane("XY").center(rc * math.cos(a), rc * math.sin(a))
              .transformed(rotate=(0, 0, CAV.ALIGN_NOTCH_ANGLE_DEG))
              .rect(L, CAV.ALIGN_NOTCH_W_MM).extrude(BOARD_T))
    for x, y in CAV.board_potting_hole_positions():
        b = b.cut(cq.Workplane("XY").center(x, y).circle(CAV.POTTING_HOLE_DIA_MM / 2).extrude(BOARD_T))
    return b


def _load(cq, p):
    if not isinstance(p, (str, pathlib.Path)):          # already a shape / workplane
        return p
    return cq.importers.importStep(str(p))


COMP_C = (0.22, 0.22, 0.24)                            # components on the boards
CACHE = REPO / ".cache" / "board_meshes"
_BOARD_CACHE: dict = {}


class _BB:
    def __init__(self, v):
        (self.xmin, self.ymin, self.zmin), (self.xmax, self.ymax, self.zmax) = v.min(0), v.max(0)
        self.xlen, self.ylen, self.zlen = (self.xmax - self.xmin, self.ymax - self.ymin,
                                           self.zmax - self.zmin)


class _Mesh:
    """A cached, already tessellated part (board + components): the few
    Workplane / Shape methods the renders use, on numpy arrays."""

    def __init__(self, v, t):
        import numpy as np
        self.v, self.t = np.asarray(v, float), np.asarray(t, np.int64)

    def translate(self, d):
        d = (d.x, d.y, d.z) if hasattr(d, "x") else d
        return _Mesh(self.v + d, self.t)

    def rotate(self, p0, p1, ang):
        import numpy as np
        p0 = np.array((p0.x, p0.y, p0.z) if hasattr(p0, "x") else p0, float)
        p1 = np.array((p1.x, p1.y, p1.z) if hasattr(p1, "x") else p1, float)
        k = (p1 - p0) / np.linalg.norm(p1 - p0)
        a = np.radians(ang)
        K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        R = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
        return _Mesh((self.v - p0) @ R.T + p0, self.t)

    def val(self):
        return self

    def BoundingBox(self):
        return _BB(self.v)


def _tess(shape, tol=0.05):
    import numpy as np
    vs, ts = shape.tessellate(tol, 0.3)
    return np.array([(p.x, p.y, p.z) for p in vs], float), np.array(ts, np.int64).reshape(-1, 3)


def _board_shapes(cq, cfg: str) -> dict:
    """{board: (pcb_mesh, parts_mesh | None)}: every board with its components
    from the configuration's tower STEP (dist/stackup_<cfg>_components.step),
    in its own frame (PCB body z 0 … BOARD_T). Reading + tessellating that
    STEP is the slow part, so the meshes are cached in .cache/board_meshes/,
    keyed on the STEP geometry (its DATA section, not the timestamped header)."""
    import hashlib
    import numpy as np
    if cfg in _BOARD_CACHE:
        return _BOARD_CACHE[cfg]
    out: dict = {}
    f = DIST / f"stackup_{cfg}_components.step"
    if not f.exists():
        _BOARD_CACHE[cfg] = out
        return out
    # key = the STEP's geometry (its DATA section): the header carries a fresh
    # timestamp on every regeneration, the geometry only changes with the boards
    raw = f.read_bytes()
    i = raw.find(b"\nDATA;")
    key = hashlib.sha1(b"v1" + raw[i if i >= 0 else 0:]).hexdigest()[:16]
    cache = CACHE / f"{cfg}_{key}.npz"
    if cache.exists():
        z = np.load(cache)
        for n in sorted({k.split("__")[0] for k in z.files}):
            pcb = _Mesh(z[f"{n}__pcb_v"], z[f"{n}__pcb_t"])
            parts = (_Mesh(z[f"{n}__parts_v"], z[f"{n}__parts_t"])
                     if f"{n}__parts_v" in z.files else None)
            out[n] = (pcb, parts)
        _BOARD_CACHE[cfg] = out
        return out
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDF import TDF_LabelSequence
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    doc = TDocStd_Document(TCollection_ExtendedString("d"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    r.ReadFile(str(f))
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    top = TDF_LabelSequence()
    st.GetFreeShapes(top)
    names = {"aft_end_board", "activation_interface", "wakeup_board", "power_board",
             "companion_compute", PAYLOAD.get(cfg, "")}
    arrays = {}
    for i in range(1, top.Length() + 1):
        comps = TDF_LabelSequence()
        st.GetComponents_s(top.Value(i), comps)
        for k in range(1, comps.Length() + 1):
            c = comps.Value(k)
            nm = TDataStd_Name()
            if not c.FindAttribute(TDataStd_Name.GetID_s(), nm):
                continue
            name = nm.Get().ToExtString()
            if name not in names:
                continue
            solids = list(cq.Shape.cast(st.GetShape_s(c)).Solids())
            if not solids:
                continue
            pcb = max(solids, key=lambda x: x.Volume())
            z0 = pcb.BoundingBox().zmin
            pv, pt = _tess(pcb)
            pv[:, 2] -= z0
            arrays[f"{name}__pcb_v"], arrays[f"{name}__pcb_t"] = pv, pt
            rest = [x for x in solids if x is not pcb]
            parts = None
            if rest:
                cv, ct = _tess(cq.Compound.makeCompound(rest), 0.08)
                cv[:, 2] -= z0
                arrays[f"{name}__parts_v"], arrays[f"{name}__parts_t"] = cv, ct
                parts = _Mesh(cv, ct)
            out[name] = (_Mesh(pv, pt), parts)
    CACHE.mkdir(parents=True, exist_ok=True)
    for old in CACHE.glob(f"{cfg}_*.npz"):          # one cache file per configuration
        old.unlink()
    np.savez_compressed(cache, **arrays)
    _BOARD_CACHE[cfg] = out
    return out


def _parts(cq, cfg: str, band: str | None):
    """[(label, workplane)] bottom → top, each in its own frame."""
    from smash.export.spacer_step import cell_centres_xy, BATT_BORE_R_MM, BATT_CELL_LENGTH_MM
    cfgd = DIST / cfg
    sl = MAXI / "sleeve" / cfg / (band or "")
    disc = _board_disc(cq)
    real = _board_shapes(cq, cfg)

    def board(name, label=None):
        """(label, pcb, PCB, [(components, COMP_C)]) — the real board when its STEP
        exists, else the plain disc."""
        if name in real:
            pcb, parts = real[name]
            return (label or name, pcb, PCB, [(parts, COMP_C)] if parts is not None else [])
        return (label or name, disc, PCB)
    rings = {p.parent.name: p for p in cfgd.glob("spacer_*/spacer_*.step")}
    pay = PAYLOAD[cfg]

    from smash.export.spacer_step import ring_spec

    def ring(lo, hi):
        p = rings.get(f"spacer_{lo}_{hi}")
        if not p:
            return None
        metal = ring_spec(f"spacer_{lo}_{hi}").is_metal
        return (f"ring {lo} / {hi} ({'7075' if metal else 'PEEK GF30'})", _load(cq, p),
                METAL if metal else PEEK_C)

    cells = None
    for x, y in cell_centres_xy():
        c = cq.Workplane("XY").center(x, y).circle(BATT_BORE_R_MM - 0.05).extrude(BATT_CELL_LENGTH_MM)
        cells = c if cells is None else cells.union(c)
    # 3 × M2 × 6 ISO 14580 low-head screws, from the aft face up into the
    # holder's taps (head Ø3.5 × 1.3 under, Ø2 shank × 6 above)
    from smash.export.aft_cap import CAP_SCREW_ANGLES_DEG, CAP_SCREW_R_MM, CAP_SCREW_HEAD_D_MM
    screws = None
    for ang in CAP_SCREW_ANGLES_DEG:
        x, y = CAP_SCREW_R_MM * math.cos(math.radians(ang)), CAP_SCREW_R_MM * math.sin(math.radians(ang))
        sc = (cq.Workplane("XY").center(x, y).circle(CAP_SCREW_HEAD_D_MM / 2).extrude(1.3)
              .union(cq.Workplane("XY").center(x, y).circle(1.0).extrude(6.0).translate((0, 0, 1.3))))
        screws = sc if screws is None else screws.union(sc)
    # (2026-11-23, user) assembly order NOSE DOWN: the sleeve stands in the
    # fixture, every part drops in on its rib and over the fixture pin
    seq = [
        ("sleeve (PEEK-LDS) into the fixture, nose down", _load(cq, sl / "core_sleeve.step"), LDS_BLACK,
         [(p, COPPER) for p in sorted((DIST / cfg / "sleeve").glob("*_sleeve_copper.step"))]),
        _payload_with_insert(cq, cfg, pay, board(pay)),
        ring("companion_compute", pay),
        board("companion_compute"),
        ring("power_board", "companion_compute"),
        board("power_board"),
        ring("wakeup_board", "power_board"),
        board("wakeup_board"),
        ring("activation_interface", "wakeup_board"),
        board("activation_interface"),
        ("battery holder (7075)", _load(cq, MAXI / "battery_holder" / "battery_holder.step"), METAL),
        ("3 × cell (pre-wired)", cells, METAL_DARK),
        ("battery floor plate (7075)", _load(cq, MAXI / "battery_floor_plate" / "battery_floor_plate.step"), METAL),
        board("aft_end_board", "aft_end_board (solder the cell leads)"),
        ("aft cap (7075 disc + PEEK-LDS crown)",
         _load(cq, MAXI / "sleeve" / "aft_end_cap" / "aft_end_cap_crown.step"), LDS_BLACK,
         [(MAXI / "sleeve" / "aft_end_cap" / "aft_end_cap_disc.step", METAL)]),
        ("3 × screw M2 × 6 ISO 14580 A2-70", screws, METAL_DARK),
    ]
    return [s for s in seq if s is not None and s[1] is not None]


def build_exploded(cfg: str, band: str | None = None):
    """([(shape, rgb)], [(n, label, anchor, od)]) — the exploded scene, NOSE
    DOWN in assembly order on the fixture (every part turned over)."""
    import cadquery as cq
    from smash.layout import cavities as CAV
    parts = _parts(cq, cfg, band)
    flip = lambda w: w.rotate((0, 0, 0), (1, 0, 0), 180)        # nose down
    items, legend, z, pin_top = [], [], 6.0, 6.0
    sleeve_h = 0.0
    for n, (label, wp, rgb, *extra) in enumerate(parts, 1):
        wp = flip(wp)
        bb = wp.val().BoundingBox()
        dz = z - bb.zmin
        items.append((wp.translate((0, 0, dz)).val(), rgb))
        for path, rgb2 in (extra[0] if extra else []):      # e.g. the sleeve's LDS copper
            items.append((flip(_load(cq, path)).translate((0, 0, dz)).val(), rgb2))   # path or shape
        if "screw" in label:
            od = ""
        elif "sleeve" in label:              # body Ø, not the neck under the nose cap
            from smash.export.sleeve_step import SLEEVE_GAP_MM, SLEEVE_WALL_MM, snap_neck_r
            od = (f"Ø{2 * (17.0 + SLEEVE_GAP_MM + SLEEVE_WALL_MM):.1f} "
                  f"(neck Ø{2 * snap_neck_r():.1f})")
        elif label.startswith("3 × cell"):
            from smash.export.spacer_step import BATT_BORE_R_MM
            od = f"Ø{2 * BATT_BORE_R_MM - 0.1:.1f} each"
        else:
            od = f"Ø{max(bb.xlen, bb.ylen):.1f}"
        # anchor right of the stack: screen-right for this view is (+1, +1, 0)
        legend.append((n, label, (19.0, 19.0, dz + (bb.zmin + bb.zmax) / 2), od))
        z = dz + bb.zmax + GAP_MM * (2.0 if "sleeve" in label else 1.0)
        if "sleeve" in label:
            sleeve_h = bb.zlen
    items.insert(0, (cq.Workplane("XY").rect(60, 60).extrude(3.0).val(), BASE_C))
    px, py = CAV.board_potting_hole_positions()[0]          # turned over: (x, −y)
    # the fixture pin at its real length: it ends inside the sleeve, at about
    # the height of the assembled stack
    items.append((cq.Workplane("XY").center(px, -py).circle(CAV.POTTING_PIN_D_MM / 2)
                  .extrude(sleeve_h - 2.0).translate((0, 0, 3.0)).val(), ZIRCONIA))
    # IKEA-style dashed alignment axes: the pin axis and the rib / notch axis
    a = -math.radians(CAV.ALIGN_NOTCH_ANGLE_DEG)            # turned over
    rr = 17.0 - CAV.ALIGN_NOTCH_DEPTH_MM / 2
    global _DASHED
    _DASHED = [((px, -py, 3.0), (px, -py, z)),
               ((rr * math.cos(a), rr * math.sin(a), 3.0), (rr * math.cos(a), rr * math.sin(a), z))]
    return items, legend


_DASHED: list = []


def _render_png(items, legend, png: pathlib.Path, width=2400, height=3300) -> None:
    """Shaded orthographic render (VTK, off-screen): flat colours + black
    feature edges + step numbers that face the camera."""
    import vtk
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    for it in items:
        shape, rgb = it[0], it[1]
        alpha = it[2] if len(it) > 2 else 1.0
        if isinstance(shape, _Mesh):                    # cached board mesh
            import numpy as np
            from vtk.util import numpy_support as nps
            pts = vtk.vtkPoints()
            pts.SetData(nps.numpy_to_vtk(np.ascontiguousarray(shape.v), deep=True))
            conn = np.hstack([np.full((len(shape.t), 1), 3, np.int64), shape.t]).ravel()
            cells = vtk.vtkCellArray()
            cells.SetCells(len(shape.t), nps.numpy_to_vtkIdTypeArray(conn, deep=True))
        else:
            verts, tris = shape.tessellate(0.05, 0.3)
            pts = vtk.vtkPoints()
            for v in verts:
                pts.InsertNextPoint(v.x, v.y, v.z)
            cells = vtk.vtkCellArray()
            for t in tris:
                cells.InsertNextCell(3, t)
        pd = vtk.vtkPolyData()
        pd.SetPoints(pts)
        pd.SetPolys(cells)
        clean = vtk.vtkCleanPolyData()
        clean.SetInputData(pd)
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(clean.GetOutputPort())
        normals.SetFeatureAngle(35)
        m = vtk.vtkPolyDataMapper()
        m.SetInputConnection(normals.GetOutputPort())
        act = vtk.vtkActor()
        act.SetMapper(m)
        prop = act.GetProperty()
        prop.SetColor(*rgb)
        prop.SetAmbient(0.35)
        prop.SetDiffuse(0.7)
        prop.SetSpecular(0.1)
        prop.SetOpacity(alpha)
        ren.AddActor(act)
        fe = vtk.vtkFeatureEdges()
        fe.SetInputConnection(clean.GetOutputPort())
        fe.BoundaryEdgesOn()
        fe.FeatureEdgesOn()
        fe.SetFeatureAngle(35)
        fe.ManifoldEdgesOff()
        fe.NonManifoldEdgesOff()
        fe.ColoringOff()
        em = vtk.vtkPolyDataMapper()
        em.SetInputConnection(fe.GetOutputPort())
        ea = vtk.vtkActor()
        ea.SetMapper(em)
        ea.GetProperty().SetColor(0.1, 0.1, 0.1)
        ea.GetProperty().SetLineWidth(1.2)
        ea.GetProperty().SetOpacity(max(alpha, 0.35))
        ren.AddActor(ea)
    global _DASHED
    for (x0, y0, z0), (x1, y1, z1) in _DASHED:      # dashed alignment axes
        L = math.dist((x0, y0, z0), (x1, y1, z1))
        t = 0.0
        while t < L:
            t2 = min(t + 2.0, L)
            ls = vtk.vtkLineSource()
            ls.SetPoint1(x0 + (x1 - x0) * t / L, y0 + (y1 - y0) * t / L, z0 + (z1 - z0) * t / L)
            ls.SetPoint2(x0 + (x1 - x0) * t2 / L, y0 + (y1 - y0) * t2 / L, z0 + (z1 - z0) * t2 / L)
            lm = vtk.vtkPolyDataMapper()
            lm.SetInputConnection(ls.GetOutputPort())
            la = vtk.vtkActor()
            la.SetMapper(lm)
            la.GetProperty().SetColor(0.15, 0.15, 0.15)
            la.GetProperty().SetLineWidth(2.0)
            ren.AddActor(la)
            t += 3.5
    _DASHED = []
    over = vtk.vtkRenderer()                         # labels on an overlay layer: never hidden
    over.SetLayer(1)
    over.InteractiveOff()
    for n, label, (x, y, z), od in legend:          # big number + name + outer diameter
        for txt, size, bold, dx in ((str(n), 46, True, 40), (f"{label}   {od}", 26, False, 110)):
            t = vtk.vtkBillboardTextActor3D()
            t.SetInput(txt)
            t.SetPosition(x, y, z)
            t.SetDisplayOffset(dx, 0)
            tp = t.GetTextProperty()
            tp.SetFontSize(size)
            tp.SetBold(bold)
            tp.SetColor(0.05, 0.05, 0.05)
            tp.SetJustificationToLeft()
            tp.SetVerticalJustificationToCentered()
            over.AddActor(t)
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetFocalPoint(0, 0, 0)
    cam.SetPosition(1.0, -1.0, 0.55)
    cam.SetViewUp(0, 0, 1)
    ren.ResetCamera()
    cam.Zoom(0.92)
    if legend:                                       # make room for the labels on the right
        cam.SetFocalPoint(*[c + d for c, d in zip(cam.GetFocalPoint(), (8.0, 8.0, 0.0))])
        cam.SetPosition(*[c + d for c, d in zip(cam.GetPosition(), (8.0, 8.0, 0.0))])
    light = vtk.vtkLight()
    light.SetLightTypeToCameraLight()
    light.SetPosition(0.6, 1.0, 1.0)
    ren.AddLight(light)
    over.SetActiveCamera(cam)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetNumberOfLayers(2)
    win.AddRenderer(ren)
    win.AddRenderer(over)
    win.SetSize(width, height)
    win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.Update()
    wr = vtk.vtkPNGWriter()
    wr.SetFileName(str(png))
    wr.SetInputConnection(w2i.GetOutputPort())
    wr.Write()


def write_exploded_view(cfg: str, out_pdf, html_to_pdf, band: str | None = None,
                        title: str = "") -> int:
    import base64
    out_pdf = pathlib.Path(out_pdf)
    items, legend = build_exploded(cfg, band)
    png = out_pdf.with_suffix(".png")
    _render_png(items, legend, png)
    img = base64.b64encode(png.read_bytes()).decode()
    swatch = lambda rgb: "background:rgb({},{},{})".format(*(int(255 * c) for c in rgb))

    key = "".join(f"<span class='sw' style='{swatch(c)}'></span>{t} &nbsp; " for t, c in
                  (("PCB", PCB), ("metal", METAL), ("PEEK GF30", PEEK_C), ("PEEK-LDS", LDS_BLACK),
                   ("LDS copper", COPPER), ("fixture pin", ZIRCONIA)))
    page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A3 portrait; margin: 12mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #111; }}
h1 {{ font-size: 18pt; margin: 0 0 4mm; }} .wrap {{ display: flex; gap: 8mm; }}
.fig {{ width: 100%; }} .fig img {{ width: 100%; max-height: 350mm; object-fit: contain; }}
.leg {{ flex: 1.3; }} table {{ border-collapse: collapse; width: 100%; }}
td {{ border-bottom: 1px solid #ccc; padding: 2mm 1mm; vertical-align: top; }}
td.n {{ font-weight: bold; font-size: 14pt; width: 10mm; }} p.note {{ font-size: 9.5pt; color: #333; }}
.sw {{ display: inline-block; width: 4mm; height: 4mm; border: 1px solid #555; margin-right: 1.5mm;
       vertical-align: middle; }}
</style></head><body><h1>{html.escape(title or 'Exploded view')}</h1>
<p>{key}</p>
<div class="wrap"><div class="fig"><img src="data:image/png;base64,{img}"></div></div>
<div class="leg">
<p class="note">Assembly order, NOSE DOWN in the fixture. Every part is keyed by the sleeve's
internal rib at 285° (board rim notches, ring gaps, holder groove, floor-plate notch) and centred
by the fixture's Ø2.9 pin through the potting holes (r 13 mm at 135°). After the vias are drilled
and soldered the tower is lifted off the pin, turned nose up and potted from the top; the nose cap
goes on after potting. Boards are drawn as plain discs (notch + potting hole) for orientation; the
tower STEP shows them with their parts.</p>
</div></body></html>"""
    htmlf = out_pdf.with_suffix(".html")
    htmlf.write_text(page)
    ok = html_to_pdf(htmlf, out_pdf)
    htmlf.unlink(missing_ok=True)
    png.unlink(missing_ok=True)
    return len(legend) if ok else 0


# ── five assembly pages (2026-11-23, user) ───────────────────────────────────
POTTING_C = (0.25, 0.45, 0.85)


def _assembled(cq, cfg: str, band: str | None):
    """[(label, shape, rgb)] at their TOWER positions (nose up, z 0 = aft face
    of aft_end_board): boards / rings / holder stacked aft → nose, sleeve /
    caps in their own (tower-frame) STEPs."""
    parts = {lbl: (wp, rgb, *ex) for lbl, wp, rgb, *ex in _parts(cq, cfg, band)}
    by = lambda key: next(v for k, v in parts.items() if k.startswith(key))
    pay = PAYLOAD[cfg]
    order = ["aft_end_board", "battery floor plate", "battery holder", "activation_interface",
             "ring activation_interface", "wakeup_board", "ring wakeup_board", "power_board",
             "ring power_board", "companion_compute", "ring companion_compute", pay]
    out, z = [], 0.0
    for key in order:
        wp, rgb, *ex = by(key)
        bb = wp.val().BoundingBox()
        out.append((key, wp.translate((0, 0, z - bb.zmin)).val(), rgb))
        for x, rgb2 in (ex[0] if ex else []):             # board components, nose insert
            out.append((key + " parts", _load(cq, x).translate((0, 0, z - bb.zmin)).val(), rgb2))
        z += bb.zlen
    # cells sit in the holder bores, on the floor plate
    from smash.export.spacer_step import BATT_FLOOR_MM
    cwp, crgb = by("3 × cell")[:2]
    out.append(("cells", cwp.translate((0, 0, BOARD_T + BATT_FLOOR_MM)).val(), crgb))
    for key in ("sleeve", "aft cap", "3 × screw"):
        wp, rgb, *ex = by(key)
        if key == "3 × screw":                              # heads on the cap's aft face, shank up
            bb = wp.val().BoundingBox()
            # head seated in the disc's counterbore: face z −2.6, counterbore
            # CAP_SCREW_CB_MM + 1.0 (boss + teeth) deep, head 1.3 tall
            from smash.export.aft_cap import CAP_SCREW_CB_MM
            wp = wp.translate((0, 0, -2.6 + CAP_SCREW_CB_MM + 1.0 - 1.3 - bb.zmin))
        out.append((key, wp.val(), rgb))
        for path, rgb2 in (ex[0] if ex else []):
            out.append((key + (" copper" if rgb2 == COPPER else " disc"), _load(cq, path).val(), rgb2))
    import cadquery as _cq
    sl = MAXI / "sleeve" / cfg / (band or "")
    nose = _load(cq, sl / "nose_cap.step").val()
    return out, z, nose


def _page_html(title, img_b64, notes, key_html):
    import html as _h
    li = "".join(f"<li>{_h.escape(n)}</li>" for n in notes)
    return (f"<section class='pg'><h1>{_h.escape(title)}</h1><p>{key_html}</p>"
            f"<div class='fig'><img src='data:image/png;base64,{img_b64}'></div>"
            f"<ol class='notes'>{li}</ol></section>")


def _payload_with_insert(cq, cfg: str, pay: str, btuple):
    """The payload tile with its bonded nose insert (radar: AoP dam; laser /
    camera: optic insert) standing on its top face."""
    base = MAXI / "sleeve" / cfg
    cands = [base / "aop_dam.step", base / "optic_insert.step"] + \
        [p for d in sorted(base.glob("*")) if d.is_dir() for p in (d / "aop_dam.step", d / "optic_insert.step")]
    ins = next((p for p in cands if p.exists()), None)
    lbl, pcb, rgb, *bex = btuple
    bex = bex[0] if bex else []
    if ins is None:
        return (lbl, pcb, rgb, bex)
    shp = _load(cq, ins)
    shp = shp.translate((0, 0, BOARD_T - shp.val().BoundingBox().zmin))
    tmp = DIST / cfg / "sleeve" / f"_{ins.stem}_on_tile.step"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shp, str(tmp))
    what = "AoP dam" if ins.stem == "aop_dam" else "optic insert"
    return (f"{pay} + {what} (bonded)", pcb, rgb,
            bex + [(tmp, (0.93, 0.90, 0.80) if what == "AoP dam" else (0.15, 0.15, 0.16))])


def _fixture_pins(cq) -> list:
    """The programmer board's aft fixture, fixture centre at the origin: one
    Mill-Max 0906 spring pin per aft-cap crown contact (r 15.2 / 16.6, as
    placed by generate_devboard) and the 3 Mill-Max 5849 locating dowels at
    the cap's locating holes."""
    import math
    import sys
    sys.path.insert(0, str(REPO))
    import generate_devboard as GDV
    from smash.export.aft_cap import CAP_LOCATE_R_MM, CAP_LOCATE_ANGLES_DEG
    m = DIST / "dev_board" / "3dmodels"
    out = []
    pin_p = m / "0906-0-15-20-76-14-11-0" / "0906-0-15-20-76-14-11-0.stp"
    dow_p = m / "5849-0-00-15-00-00-03-0" / "5849-0-00-15-00-00-03-0.stp"
    pin = (_load(cq, pin_p) if pin_p.exists() else
           cq.Workplane("XY").circle(0.9).extrude(5.3))
    dow = (_load(cq, dow_p).translate((0, 0, 6.5 - 8.76)) if dow_p.exists() else
           cq.Workplane("XY").circle(0.75).extrude(6.5))
    for tooth, ang, _net, _label, role in GDV.aft_contacts():
        if role in ("screw", "key"):
            continue
        r, a = GDV.FIXTURE_R[tooth % 2], math.radians(ang)
        out.append((pin.translate((r * math.cos(a), r * math.sin(a), 0)).val(), (0.86, 0.70, 0.30)))
    for ang in CAP_LOCATE_ANGLES_DEG:
        a = math.radians(ang)
        out.append((dow.translate((CAP_LOCATE_R_MM * math.cos(a), CAP_LOCATE_R_MM * math.sin(a), 0)).val(),
                    METAL))
    return out


def write_assembly_pages(cfg: str, out_pdf, html_to_pdf, band: str | None = None,
                         name: str = "") -> int:
    """Five pages: 1 upside-down assembly (exploded), 2 vias + copper, 3 potting,
    4 parylene coat, 5 nose cap. Returns the page count (0 on failure)."""
    import base64
    import cadquery as cq
    from smash.layout import cavities as CAV
    out_pdf = pathlib.Path(out_pdf)
    tmp = out_pdf.with_suffix(".png")
    flip = lambda sh: sh.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180)

    def render(items, labels=()):
        _render_png(items, list(labels), tmp)
        b = base64.b64encode(tmp.read_bytes()).decode()
        tmp.unlink(missing_ok=True)
        return b

    sw = lambda rgb: "background:rgb({},{},{})".format(*(int(255 * c) for c in rgb))
    key = "".join(f"<span class='sw' style='{sw(c)}'></span>{t} &nbsp; " for t, c in
                  (("PCB", PCB), ("metal", METAL), ("PEEK GF30", PEEK_C), ("PEEK-LDS", LDS_BLACK),
                   ("LDS copper", COPPER), ("fixture pin", ZIRCONIA), ("potting", POTTING_C)))
    pages = []
    # 1 — exploded, nose down
    items, legend = build_exploded(cfg, band)
    pages.append(_page_html(f"{name} — step 1: assembly, nose down in the fixture", render(items, legend), [
        "Stand the sleeve in the fixture, nose end down, over the Ø2.9 fixture pin.",
        "Drop the parts in, in the numbered order: each one on the sleeve's internal rib at 285° "
        "(board rim notches, ring gaps, holder groove, floor-plate notch) and over the pin "
        "(potting holes, r 13 mm at 135°).",
        "Cells into the open holder; floor plate; aft_end_board; solder the cell leads on its "
        "aft face (In52/Sn48). From here on the cells are live: nothing above 85 °C.",
        "Aft cap (7075 disc + PEEK-LDS crown), access holes over the clamp tabs; 3 × M2 × 6 "
        "screws through the disc, aft_end_board and floor plate into the holder's taps."], key))
    # assembled tower (nose up)
    asm, z_pay, nose = _assembled(cq, cfg, band)
    base = cq.Workplane("XY").rect(60, 60).extrude(3.0).val()
    px, py = CAV.board_potting_hole_positions()[0]
    # 2 — vias + copper, still on the fixture (nose down)
    zs = max(sh.BoundingBox().zmax for _k, sh, _c in asm)
    f2 = [(flip(sh).translate(cq.Vector(0, 0, zs + 3.0)), rgb) for _k, sh, rgb in asm]
    f2 += [(base, BASE_C), (cq.Workplane("XY").center(px, -py).circle(CAV.POTTING_PIN_D_MM / 2)
                           .extrude(zs).translate((0, 0, 3.0)).val(), ZIRCONIA)]
    pages.append(_page_html(f"{name} — step 2: sleeve vias and copper (still on the fixture)",
                            render(f2), [
        "Laser-drill each via (CO2, Ø0.3-0.4 mm) through the centre of its LDS pad and the sleeve "
        "wall; the CO2 laser stops on the castellation copper. Positions are fixed relative to the "
        "fixture pin and the sleeve rib: one program per configuration.",
        "Clean the laser residue off the castellation copper (your process); fill with Sn42Bi58 "
        "(138 °C) by solder-jet or laser soldering.",
        "Bridge each aft-cap lane to its sleeve lane across the cap / sleeve joint with Sn42Bi58.",
        "Check the continuity of every lane."], key))
    # 3 — potting, nose up, sleeve see-through
    fill = (cq.Workplane("XY").circle(17.1).extrude(z_pay + 0.5).val(), POTTING_C, 0.35)
    f3 = [(sh, rgb, 0.18 if k.startswith("sleeve") else 1.0) for k, sh, rgb in asm
          if not k.endswith("copper")] + [fill]
    pages.append(_page_html(f"{name} — step 3: potting, nose up", render(f3), [
        "Lift the tower off the fixture (the pin comes out) and stand it nose up.",
        "Plug the IR light pipes; the radome pocket / lens light tube stay air.",
        "Pour from the top down the potting channel (the boards' Ø3 holes) so it fills from the "
        "aft end up; the sleeve's inner grooves vent to the top.",
        "Stop when the potting comes up through the payload tile's potting hole and spreads ≈ 0.5 mm "
        "over it. Stycast 1090 SI + Cat 23LV: vacuum degas, cure 4-6 h at 45 °C (≤ 85 °C, cells)."],
        key))
    # 4 — nose cap (press-fit, no adhesive)
    f4 = [(sh, rgb) for _k, sh, rgb in asm] + [(nose.translate(cq.Vector(0, 0, 12.0)), LDS_BLACK)]
    pages.append(_page_html(f"{name} — step 4: nose cap", render(f4), [
        "(optional) Apply a structural adhesive to the sleeve neck (e.g. Loctite EA 9466); for the "
        "best bond to PEEK, plasma-activate the neck and the cap bore first.",
        "Press the Ø40 cap over the sleeve neck (0.06 mm radial interference) — permanent."], key))
    # 5 — parylene over everything, incl. the cap joint
    f5 = [(sh, rgb) for _k, sh, rgb in asm] + [(nose, LDS_BLACK)] + [
        (cq.Workplane("XY").circle(20.0 + 0.4).circle(17.9).extrude(z_pay + 6.2).translate((0, 0, -2.4)).val(),
         (0.6, 0.85, 1.0), 0.25)]
    pages.append(_page_html(f"{name} — step 5: parylene coat", render(f5), [
        "Parylene C, 15-25 µm, vapour-deposited at room temperature over the whole tower: sleeve, "
        "via fills, aft cap, nose cap and their joints (drawn as a light shell) — it seals the "
        "nose-cap joint.",
        "Mask only the aft cap's contact crown.",
        "It also insulates the sleeve lanes; no measurable effect on the antennas."], key))
    # 6 — bench validation on the test fixture (programmer board + aft fixture)
    coll_p = DIST / "dev_board" / "fixture_collar.step"
    board = cq.Workplane("XY").rect(70, 70).extrude(1.6).translate((0, 0, -1.6)).val()
    f6 = [(board, PCB)] + _fixture_pins(cq)
    if coll_p.exists():
        f6.append((_load(cq, coll_p).val(), (0.85, 0.85, 0.82), 0.35))   # see-through
    lift = 8.0 + 2.4 + 6.0                                   # tower shown just above the collar
    f6 += [(sh.translate(cq.Vector(0, 0, lift)), rgb) for _k, sh, rgb in asm]
    f6.append((nose.translate(cq.Vector(0, 0, lift)), LDS_BLACK))
    pages.append(_page_html(f"{name} — step 6: bench validation on the test fixture", render(f6), [
        "Seat the tower, aft cap down, in the programmer board's aft fixture (drawn: the ring of "
        "spring pins, one per crown contact, the 3 locating dowels and the see-through guide "
        "collar): the collar over the sleeve, the aft cap's 3 locating holes on the dowels, its "
        "crown contacts on the spring pins. Hold it down by hand (≈ 3-5 kg); the three SEAT LEDs lit = seated flat.",
        "The programmer powers the tower through the aft cap's EXT POWER contact (≈ 5.6 V, metered) "
        "and runs the validation of the electronics per our test specification and firmware.",
        "Record the result against the tower's serial number.",
        "(optional) Lot audit on sample towers: CT scan + bench test before and after the shock "
        "test, compared per serial number."], key))
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{name} — assembly steps</title><style>
@page {{ size: A3 portrait; margin: 12mm; }}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #111; }}
.pg {{ page-break-after: always; }} .pg:last-child {{ page-break-after: auto; }}
h1 {{ font-size: 18pt; margin: 0 0 3mm; }}
.fig img {{ width: 100%; height: 300mm; object-fit: contain; }}
ol.notes {{ font-size: 11pt; }} ol.notes li {{ margin: 1mm 0; }}
.sw {{ display: inline-block; width: 4mm; height: 4mm; border: 1px solid #555; margin-right: 1.5mm;
       vertical-align: middle; }}
</style></head><body>{''.join(pages)}</body></html>"""
    htmlf = out_pdf.with_suffix(".html")
    htmlf.write_text(doc)
    ok = html_to_pdf(htmlf, out_pdf)
    htmlf.unlink(missing_ok=True)
    return len(pages) if ok else 0
