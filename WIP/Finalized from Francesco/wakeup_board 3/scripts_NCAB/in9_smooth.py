"""wakeup_board - liscia le zone del power path su In9.Cu (review Sjoert: acid trap / scalette).

Le zone PWRPATH_In9_* nate dal raster Voronoi da 0.2 mm hanno contorni a scaletta. Qui la forma
(e quindi la connettivita) resta quella attuale, ma ogni contorno viene:
  1. semplificato con Douglas-Peucker (EPS): le scalette diventano diagonali dritte
  2. chiuso e aperto con raggio RND (angoli acuti arrotondati: niente acid trap)
  3. distanziato di GAP dalle zone delle altre net gia processate
Una zona che non contiene nessuna via della propria net (rame isolato) viene tolta e la sua area
passa a REG_IN_MAIN, che la circonda.
Uso: python.exe in9_smooth.py <board.kicad_pcb>
"""
import sys, math
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
b = p.LoadBoard(path)
EPS = 0.15          # tolleranza Douglas-Peucker (scalino raster 0.2 mm)
RND = 0.25          # raggio di arrotondamento angoli
GAP = 0.30          # distanza tra zone di net diverse
ERR = mm(0.005)
ROUND = p.CORNER_STRATEGY_ROUND_ALL_CORNERS
ORDER = ["REG_IN_MAIN", "BAT_RAW", "BAT_PROT", "BOOST_OUT"]


def dp(pts, eps):
    """Douglas-Peucker su una polilinea aperta"""
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    best, idx = -1, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs(dy * (x - x0) - dx * (y - y0)) / L if L > 0 else math.hypot(x - x0, y - y0)
        if d > best:
            best, idx = d, i
    if best <= eps:
        return [pts[0], pts[-1]]
    return dp(pts[:idx + 1], eps)[:-1] + dp(pts[idx:], eps)


def dp_closed(pts, eps):
    # spezza l'anello nel vertice piu lontano dal primo, cosi gli estremi sono stabili
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    a = dp(pts[:far + 1], eps)
    c = dp(pts[far:] + [pts[0]], eps)
    return a[:-1] + c[:-1]


def chain(pts):
    ch = p.SHAPE_LINE_CHAIN()
    for x, y in pts:
        ch.Append(mm(x), mm(y))
    ch.SetClosed(True)
    return ch


zones = {z.GetNetname(): z for z in b.Zones() if z.GetZoneName().startswith("PWRPATH_In9_")}
vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.IsOnLayer(p.In9_Cu)]
for net, z in list(zones.items()):
    if net != "REG_IN_MAIN" and not any(v.GetNetname() == net and z.Outline().Contains(v.GetPosition()) for v in vias):
        main = zones["REG_IN_MAIN"].Outline()
        main.BooleanAdd(z.Outline())
        main.Simplify()
        b.Remove(z)
        del zones[net]
        print(f"  {net:12s} nessuna via propria nella zona: tolta, area data a REG_IN_MAIN")
done = p.SHAPE_POLY_SET()
for net in [n for n in ORDER if n in zones]:
    z = zones[net]
    src = z.Outline()
    n0 = src.FullPointCount()
    ps = p.SHAPE_POLY_SET()
    for k in range(src.OutlineCount()):
        o = src.COutline(k)
        pts = [(tomm(o.CPoint(i).x), tomm(o.CPoint(i).y)) for i in range(o.PointCount())]
        ps.AddOutline(chain(dp_closed(pts, EPS)))
        for h in range(src.HoleCount(k)):
            ho = src.CHole(k, h)
            hp = [(tomm(ho.CPoint(i).x), tomm(ho.CPoint(i).y)) for i in range(ho.PointCount())]
            ps.AddHole(chain(dp_closed(hp, EPS)), k)
    ps.Simplify()
    ps.Inflate(mm(RND), ROUND, ERR, True); ps.Inflate(-mm(RND), ROUND, ERR, True)     # chiusura
    ps.Inflate(-mm(RND), ROUND, ERR, True); ps.Inflate(mm(RND), ROUND, ERR, True)     # apertura
    if done.OutlineCount():
        keep = done.CloneDropTriangulation()
        keep.Inflate(mm(GAP), ROUND, ERR, True)
        ps.BooleanSubtract(keep)
    ps.Simplify()
    done.BooleanAdd(ps)
    z.Outline().RemoveAllContours()
    for k in range(ps.OutlineCount()):
        z.Outline().AddPolygon(ps.Polygon(k))
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
    print(f"  {net:12s} vertici {n0:4d} -> {ps.FullPointCount():4d}  contorni {ps.OutlineCount()}  area {ps.Area() / 1e12:6.1f} mm2")

p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)
print("In9: zone lisciate e riempite")
