"""wakeup_board - review Sjoert: "each FLEX_GND should have its own microvia or via".

Per ogni pad SMD FLEX_GND senza via propria (nessuna via, oppure via condivisa con altri pad: la
via resta al pad piu vicino) propone una MICROVIA 0.25/0.10 verso il piano FLEX_GND adiacente:
  pad sul top    -> microvia F.Cu-In1.Cu   (In1 = piano FLEX_GND)
  pad sul bottom -> microvia In12.Cu-B.Cu  (In12 = piano FLEX_GND)
Prima prova DENTRO il pad (via-in-pad: microvia NCAB riempite e ricoperte), con la microvia tutta
contenuta nel pad; se non c'e posto la mette appena fuori con una pista corta 0.15 mm.
Controlli: rame di altre net 0.10, foro-foro 0.25 (via meccanici) / 0.15 (microvia), piano GND
riempito nel punto (la microvia deve davvero toccare la massa).
Uso: python.exe gnd_vias.py <board.kicad_pcb> [--apply]
"""
import sys, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path, APPLY = sys.argv[1], "--apply" in sys.argv
b = p.LoadBoard(path)
p.ZONE_FILLER(b).Fill(b.Zones())
NET = "FLEX_GND"
DV, DH, TW = 0.25, 0.10, 0.15
C_CU, C_HH_MECH, C_HH_MICRO, C_PLANE = 0.10, 0.25, 0.15, 0.15

net = b.FindNet(NET)
V = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
T = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
P = [(f, q) for f in b.GetFootprints() for q in f.Pads()]
gp = [(f, q) for f, q in P if q.GetNetname() == NET and q.GetAttribute() == p.PAD_ATTRIB_SMD]
plane = {L: [z for z in b.Zones() if z.GetNetname() == NET and z.GetLayer() == L and not z.IsTeardropArea()][0]
         for L in (p.In1_Cu, p.In12_Cu)}


def side(q):
    return p.F_Cu if q.IsOnLayer(p.F_Cu) else p.B_Cu


# ---- quali via servono gia quale pad
users = collections.defaultdict(set)
for f, q in gp:
    L = side(q)
    for v in V:
        if v.GetNetname() == NET and v.IsOnLayer(L) and q.HitTest(v.GetPosition()):
            users[v.m_Uuid.AsString()].add((f.GetReference(), q.GetNumber()))
    for t in T:
        if t.GetNetname() != NET or t.GetLayer() != L:
            continue
        for e, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            if q.HitTest(e):
                for v in V:
                    if v.GetNetname() == NET and (v.GetPosition() - o).EuclideanNorm() < v.GetWidth(L) // 2:
                        users[v.m_Uuid.AsString()].add((f.GetReference(), q.GetNumber()))
vpos = {v.m_Uuid.AsString(): v.GetPosition() for v in V}
padobj = {(f.GetReference(), q.GetNumber()): (f, q) for f, q in gp}
owner = set()
for vid, us in users.items():
    best = min(us, key=lambda u: (padobj[u][1].GetPosition() - vpos[vid]).EuclideanNorm())
    owner.add(best)
need = [(f, q) for f, q in gp if (f.GetReference(), q.GetNumber()) not in owner]
print(f"pad SMD {NET}: {len(gp)}, con via propria {len(owner)}, da servire {len(need)}")

new_vias = []       # (pos, layers) gia proposte


def via_free(c, layers, pad_self):
    circ = p.SHAPE_CIRCLE(c, mm(DV / 2))
    hole = mm(DH / 2)
    for v in V:
        d = (v.GetPosition() - c).EuclideanNorm()
        micro = v.GetViaType() == p.VIATYPE_MICROVIA
        if d < hole + v.GetDrill() // 2 + mm(C_HH_MICRO if micro else C_HH_MECH):
            return False
        if v.GetNetname() != NET and any(v.IsOnLayer(l) for l in layers) and d < mm(DV / 2) + v.GetWidth(p.F_Cu) // 2 + mm(C_CU):
            return False
    for c2, l2 in new_vias:
        if (c2 - c).EuclideanNorm() < 2 * hole + mm(C_HH_MICRO):
            return False
    for t in T:
        if t.GetNetname() != NET and t.GetLayer() in layers and t.GetEffectiveShape(t.GetLayer()).Collide(circ, mm(C_CU)):
            return False
    for f, q in P:
        if q is pad_self or q.GetNetname() == NET:
            continue
        for l in layers:
            if q.IsOnLayer(l) and q.GetEffectiveShape(l).Collide(circ, mm(C_CU)):
                return False
    # deve toccare davvero il piano di massa
    pl = layers[1] if layers[0] in (p.F_Cu,) else layers[0]
    fill = plane[pl].GetFilledPolysList(pl)
    if not fill.Contains(c):
        return False
    for t in T:
        if t.GetNetname() != NET and t.GetLayer() == pl and t.GetEffectiveShape(pl).Collide(circ, mm(C_PLANE)):
            return False
    return True


def inside_pad(q, L, c):
    s = q.GetSize(L)
    if min(s.x, s.y) < mm(DV):          # sfere BGA piu piccole della microvia: solo centrata
        return (c - q.GetPosition()).EuclideanNorm() == 0
    r = mm(DV / 2)
    return all(q.HitTest(p.VECTOR2I(int(c.x + r * math.cos(a)), int(c.y + r * math.sin(a))))
               for a in [k * math.pi / 8 for k in range(16)]) and q.HitTest(c)


def track_free(a, c, L):
    seg = p.SHAPE_SEGMENT(a, c, mm(TW))
    for t in T:
        if t.GetNetname() != NET and t.GetLayer() == L and t.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for f, q in P:
        if q.GetNetname() != NET and q.IsOnLayer(L) and q.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for v in V:
        if v.GetNetname() != NET and v.IsOnLayer(L):
            thr = v.GetViaType() == p.VIATYPE_THROUGH
            if seg.Collide(p.SHAPE_CIRCLE(v.GetPosition(), v.GetWidth(L) // 2), mm(0.15 if thr else C_CU)):
                return False
    return True


rows = []
for f, q in sorted(need, key=lambda x: (x[0].GetReference(), x[1].GetNumber())):
    L = side(q)
    layers = (p.F_Cu, p.In1_Cu) if L == p.F_Cu else (p.In12_Cu, p.B_Cu)
    o = q.GetPosition()
    found = None
    # 1) dentro il pad, dal centro verso fuori
    for d in [k * 0.025 for k in range(0, 13)]:
        for a in range(0, 360, 15 if d else 360):
            c = p.VECTOR2I(int(o.x + mm(d) * math.cos(math.radians(a))), int(o.y + mm(d) * math.sin(math.radians(a))))
            if inside_pad(q, L, c) and via_free(c, layers, q):
                found = ("nel pad", c, None)
                break
        if found:
            break
    # 2) fuori dal pad, con pista corta dal centro del pad
    if not found:
        for d in [0.35 + k * 0.05 for k in range(0, 15)]:
            for a in range(0, 360, 10):
                c = p.VECTOR2I(int(o.x + mm(d) * math.cos(math.radians(a))), int(o.y + mm(d) * math.sin(math.radians(a))))
                if not q.HitTest(c) and via_free(c, layers, q) and track_free(o, c, L):
                    found = ("fuori %.2f mm" % d, c, o)
                    break
            if found:
                break
    lname = "F.Cu-In1" if L == p.F_Cu else "In12-B.Cu"
    if found:
        new_vias.append((found[1], layers))
        rows.append((f.GetReference(), q.GetNumber(), lname, found[0], tomm(found[1].x), tomm(found[1].y), found))
    else:
        rows.append((f.GetReference(), q.GetNumber(), lname, "NESSUN POSTO", tomm(o.x), tomm(o.y), None))

print(f"{'pad':40s} {'microvia':10s} {'dove':14s} {'X':>8s} {'Y':>8s}")
for r in rows:
    print(f"{r[0] + '.' + r[1]:40s} {r[2]:10s} {r[3]:14s} {r[4]:8.3f} {r[5]:8.3f}")

if APPLY:
    for ref, num, lname, how, x, y, found in rows:
        if not found:
            continue
        L = p.F_Cu if lname.startswith("F") else p.B_Cu
        v = p.PCB_VIA(b)
        v.SetViaType(p.VIATYPE_MICROVIA)
        v.SetPosition(found[1])
        v.SetLayerPair(p.F_Cu, p.In1_Cu) if L == p.F_Cu else v.SetLayerPair(p.In12_Cu, p.B_Cu)
        v.SetWidth(mm(DV))
        v.SetDrill(mm(DH))
        v.SetNet(net)
        b.Add(v)
        if found[2] is not None:
            t = p.PCB_TRACK(b)
            t.SetStart(found[2]); t.SetEnd(found[1]); t.SetWidth(mm(TW)); t.SetLayer(L); t.SetNet(net)
            b.Add(t)
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(path, b)
    print("salvato")
