"""wakeup_board: piazzamento mirato dei componenti critici (RF, SMPS, boost, clock).
Cerca per ogni componente la posizione piu vicina al pin di destinazione senza collisioni
(courtyard, pad, via, piste). Con --apply salva; altrimenti solo analisi.
Uso: python.exe place_opt.py <board.kicad_pcb> [--apply]
"""
import sys, math, pcbnew as p
mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]; APPLY = "--apply" in sys.argv
b = p.LoadBoard(path)
R_BOARD = 16.2          # i pad devono restare dentro questo raggio
STEP = 0.2
MAXR = 7.0

def fp(ref): return b.FindFootprintByReference(ref)
def padpos(ref, num):
    f = fp(ref)
    for pd in f.Pads():
        if pd.GetNumber() == num: return (tomm(pd.GetPosition().x), tomm(pd.GetPosition().y))
    raise KeyError(f"{ref}.{num}")
def ballpos(num): return padpos("U_WBA", num)

def courtyard(f):
    ps = f.GetCourtyard(p.F_CrtYd if not f.IsFlipped() else p.B_CrtYd)
    if ps.OutlineCount() == 0:
        ps = p.SHAPE_POLY_SET()
        bb = f.GetBoundingBox(False, False)
        ch = p.SHAPE_LINE_CHAIN()
        for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()),
                     (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
            ch.Append(x, y)
        ch.SetClosed(True); ps.AddOutline(ch)
    return ps

def overlaps(a, c):
    t = p.SHAPE_POLY_SET(a); t.BooleanIntersection(c)
    return t.OutlineCount() > 0

vias = [(tomm(t.GetPosition().x), tomm(t.GetPosition().y), tomm(t.GetWidth(p.F_Cu)) / 2)
        for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
segs = [(tomm(t.GetStart().x), tomm(t.GetStart().y), tomm(t.GetEnd().x), tomm(t.GetEnd().y),
         tomm(t.GetWidth()) / 2, t.GetLayer())
        for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]

def segdist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

BIGCY = 25.0    # courtyard piu grandi di cosi (connettori LGA) -> si usano i pad

def cyarea(f):
    ps = courtyard(f)
    return ps.Area() / 1e12 if ps.OutlineCount() else 0.0

def padboxes(f):
    out = []
    for pd in f.Pads():
        bb = pd.GetBoundingBox()
        out.append((tomm(bb.GetLeft()), tomm(bb.GetTop()), tomm(bb.GetRight()), tomm(bb.GetBottom())))
    return out

def boxes_hit(a, bxs, margin):
    for c in bxs:
        if (a[0] - margin < c[2] and a[2] + margin > c[0]
                and a[1] - margin < c[3] and a[3] + margin > c[1]):
            return True
    return False

def feasible(f, others_small, pad_obst, lay):
    cy = courtyard(f)
    for o in others_small:
        if o.GetLayer() != f.GetLayer(): continue
        if overlaps(cy, courtyard(o)): return False
    for a in padboxes(f):
        if boxes_hit(a, pad_obst, 0.15): return False
    for pd in f.Pads():
        x, y = tomm(pd.GetPosition().x), tomm(pd.GetPosition().y)
        r = max(tomm(pd.GetSize(p.F_Cu).x), tomm(pd.GetSize(p.F_Cu).y)) / 2
        if math.hypot(x, y) + r > R_BOARD: return False
        for vx, vy, vr in vias:
            if math.hypot(x - vx, y - vy) < r + vr + 0.10: return False
        for x1, y1, x2, y2, hw, sl in segs:
            if sl == lay and segdist(x, y, x1, y1, x2, y2) < r + hw + 0.10: return False
    return True

def optimize(ref, targets, maxr=MAXR, xmax=None, xmin=None):
    """targets: [(pad, (x,y), peso)] - minimizza la somma pesata delle distanze."""
    f = fp(ref)
    others = [o for o in b.GetFootprints() if o.GetReference() != ref]
    others_small = [o for o in others if cyarea(o) < BIGCY]
    pad_obst = [bx for o in others if o.GetLayer() == f.GetLayer() for bx in padboxes(o)]
    p0, rot0 = f.GetPosition(), f.GetOrientationDegrees()
    cx = sum(t[1][0] for t in targets) / len(targets)
    cy0 = sum(t[1][1] for t in targets) / len(targets)
    def cost():
        s = 0
        for num, (tx, ty), w in targets:
            x, y = padpos(ref, num)
            s += w * math.hypot(x - tx, y - ty)
        return s
    best = None
    before = cost()
    n = int(maxr / STEP)
    for rot in (0, 90, 180, 270):
        f.SetOrientationDegrees(rot)
        for iy in range(-n, n + 1):
            for ix in range(-n, n + 1):
                x, y = cx + ix * STEP, cy0 + iy * STEP
                if math.hypot(x - cx, y - cy0) > maxr: continue
                if xmax is not None and x > xmax: continue
                if xmin is not None and x < xmin: continue
                f.SetPosition(p.VECTOR2I(mm(x), mm(y)))
                c = cost()
                if best and c >= best[0]: continue
                if not feasible(f, others_small, pad_obst, f.GetLayer()): continue
                best = (c, x, y, rot)
    if best:
        f.SetPosition(p.VECTOR2I(mm(best[1]), mm(best[2]))); f.SetOrientationDegrees(best[3])
        print(f"  {ref:12s} costo {before:6.2f} -> {best[0]:6.2f} mm   pos ({best[1]:6.2f},{best[2]:6.2f}) rot {best[3]:3.0f}")
    else:
        f.SetPosition(p0); f.SetOrientationDegrees(rot0)
        print(f"  {ref:12s} nessuna posizione libera trovata (costo attuale {before:.2f})")
    return best is not None

print("== boost: anello di commutazione compatto attorno a U_BOOST")
optimize("L_PWR", [("2", padpos("U_BOOST", "1"), 1.0), ("1", padpos("U_BOOST", "3"), 0.5)])
for ref in ["CBOOST_IN1_1", "CBOOST_IN1_2", "CBOOST_IN1_3", "CBOOST_IN1_4", "CBOOST_IN1_5", "CBOOST_IN2"]:
    optimize(ref, [("1", padpos("U_BOOST", "3"), 1.0), ("2", padpos("U_BOOST", "2"), 0.6)], maxr=5.0)
for ref in ["CBOOST_OUT1", "CBOOST_OUT2"]:
    optimize(ref, [("1", padpos("U_BOOST", "5"), 1.0), ("2", padpos("U_BOOST", "2"), 0.6)], maxr=5.0)

if APPLY:
    p.ZONE_FILLER(b).Fill(b.Zones()); p.SaveBoard(path, b); print("salvato")
else:
    print("(analisi soltanto, nessun salvataggio)")
