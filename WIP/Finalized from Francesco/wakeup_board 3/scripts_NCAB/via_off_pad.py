"""wakeup_board - review Sjoert: "some vias only connect in the annular ring".

La via REG_IN_MAIN vicino a U_BOOST.3 tocca il pad solo con uno spicchio dell'anello e non ha piste.
La sposta nel punto piu vicino FUORI dal pad (distacco >= GAP_PAD dal rame del pad) dove:
  via 0.45/0.20: via-pista 0.15, via-via 0.25, pad 0.10, foro-foro 0.25 (regole NCAB/FAB)
  e ancora dentro il riempimento del piano della sua net su In9 (deve restare collegata al piano)
e la collega al pad con una pista TW su F.Cu (dal centro del pad), controllata a 0.10/0.15.
Uso: python.exe via_off_pad.py <board.kicad_pcb> [--apply]
"""
import sys, math
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path, APPLY = sys.argv[1], "--apply" in sys.argv
b = p.LoadBoard(path)
p.ZONE_FILLER(b).Fill(b.Zones())
REF, PADNUM, NEAR = "U_BOOST", "3", (-6.63, 4.95)
D, DRILL, TW, GAP_PAD = 0.45, 0.20, 0.25, 0.10
C_VT, C_VV, C_CU, C_HH = 0.15, 0.25, 0.10, 0.25
PLANE = p.In9_Cu

V = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
T = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
P = [(f, q) for f in b.GetFootprints() for q in f.Pads()]
CU = list(b.GetEnabledLayers().CuStack())
fp = [f for f in b.GetFootprints() if f.GetReference() == REF][0]
pad = [q for q in fp.Pads() if q.GetNumber() == PADNUM][0]
via = min(V, key=lambda v: (v.GetPosition() - p.VECTOR2I(mm(NEAR[0]), mm(NEAR[1]))).EuclideanNorm())
net = via.GetNetCode()
assert via.GetNetname() == pad.GetNetname(), "via e pad di net diverse"
L = pad.GetPrincipalLayer()
plane_fill = [z for z in b.Zones() if z.GetNetCode() == net and z.GetLayer() == PLANE and not z.IsTeardropArea()][0]
print(f"via {via.GetNetname()} ({tomm(via.GetPosition().x):.3f},{tomm(via.GetPosition().y):.3f}) -> pad {REF}.{PADNUM}")


def via_ok(c):
    circ = p.SHAPE_CIRCLE(c, mm(D / 2))
    if pad.GetEffectiveShape(L).Collide(circ, mm(GAP_PAD)):
        return False
    if not plane_fill.GetFilledPolysList(PLANE).Contains(c):
        return False
    for o in V:
        if o is via or o.m_Uuid.AsString() == via.m_Uuid.AsString():
            continue
        d = (o.GetPosition() - c).EuclideanNorm()
        if d < mm(DRILL / 2) + o.GetDrill() // 2 + mm(C_HH):
            return False
        if o.GetNetCode() != net:
            thr = o.GetViaType() == p.VIATYPE_THROUGH
            if d < mm(D / 2) + o.GetWidth(p.F_Cu) // 2 + mm(C_VV if thr else C_CU):
                return False
    for t in T:
        if t.GetNetCode() != net and t.GetEffectiveShape(t.GetLayer()).Collide(circ, mm(C_VT)):
            return False
    for f, q in P:
        if q.GetNetCode() == net:
            continue
        for l in CU:
            if q.IsOnLayer(l) and q.GetEffectiveShape(l).Collide(circ, mm(C_CU)):
                return False
    return True


def trk_ok(a, c):
    seg = p.SHAPE_SEGMENT(a, c, mm(TW))
    for t in T:
        if t.GetNetCode() != net and t.GetLayer() == L and t.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for f, q in P:
        if q.GetNetCode() != net and q.IsOnLayer(L) and q.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for o in V:
        if o.GetNetCode() != net and o.IsOnLayer(L):
            thr = o.GetViaType() == p.VIATYPE_THROUGH
            if seg.Collide(p.SHAPE_CIRCLE(o.GetPosition(), o.GetWidth(L) // 2), mm(C_VT if thr else C_CU)):
                return False
    return True


o = via.GetPosition()
a = pad.GetPosition()
best = None
for k in range(0, 41):
    d = k * 0.025
    for ang in range(0, 360, 10 if d else 360):
        c = p.VECTOR2I(int(o.x + mm(d) * math.cos(math.radians(ang))), int(o.y + mm(d) * math.sin(math.radians(ang))))
        if via_ok(c) and trk_ok(a, c):
            best = (d, c)
            break
    if best:
        break
if not best:
    sys.exit("nessuna posizione valida entro 1 mm")
d, c = best
print(f"nuova posizione ({tomm(c.x):.3f},{tomm(c.y):.3f}), spostamento {d:.3f} mm, "
      f"pista {TW} mm su {b.GetLayerName(L)} lunga {tomm((c - a).EuclideanNorm()):.3f} mm dal centro del pad")

if APPLY:
    for z in [z for z in b.Zones() if z.IsTeardropArea() and z.GetNetCode() == net and z.Outline().Collide(o, mm(D))]:
        b.Remove(z)
    via.SetPosition(c)
    t = p.PCB_TRACK(b)
    t.SetStart(a); t.SetEnd(c); t.SetWidth(mm(TW)); t.SetLayer(L); t.SetNetCode(net)
    b.Add(t)
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(path, b)
    print("salvato")
