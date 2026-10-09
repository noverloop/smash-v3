"""wakeup_board - review Sjoert: acid trap (angoli acuti tra piste).

Dove due segmenti della stessa net e strato si incontrano formando un angolo interno < 90 gradi
(e nel vertice non c'e pad ne via), l'angolo viene smussato: i due segmenti vengono accorciati di
d dal vertice e uniti da un tratto corto. Ne nascono due angoli ottusi (90 + angolo/2).
d parte da 0.30 mm (max 45 % del segmento piu corto) e scende fino a 0.08 se serve per rispettare
0.10 da piste/pad di altre net e 0.15 dalle via passanti.
Uso: python.exe fix_acute.py <board.kicad_pcb> [--apply]
"""
import sys, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path, APPLY = sys.argv[1], "--apply" in sys.argv
C_CU, C_VT = 0.10, 0.15
b = p.LoadBoard(path)
T = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
V = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
P = [(f, q) for f in b.GetFootprints() for q in f.Pads()]

ends = collections.defaultdict(list)
for t in T:
    for a, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
        ends[(t.GetLayer(), t.GetNetCode(), a.x, a.y)].append((t, o))


def occupied(L, n, pt):
    for v in V:
        if v.IsOnLayer(L) and (v.GetPosition() - pt).EuclideanNorm() <= v.GetWidth(L) // 2:
            return True
    for f, q in P:
        if q.IsOnLayer(L) and q.HitTest(pt):
            return True
    return False


def chord_ok(L, n, a, c, w):
    seg = p.SHAPE_SEGMENT(a, c, w)
    for o in T:
        if o.GetNetCode() != n and o.GetLayer() == L and o.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for f, q in P:
        if q.GetNetCode() != n and q.IsOnLayer(L) and q.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for v in V:
        if v.GetNetCode() != n and v.IsOnLayer(L):
            thr = v.GetViaType() == p.VIATYPE_THROUGH
            if seg.Collide(p.SHAPE_CIRCLE(v.GetPosition(), v.GetWidth(L) // 2), mm(C_VT if thr else C_CU)):
                return False
    return True


done, skipped, other = [], [], []
used = set()
for (L, n, x, y), lst in ends.items():
    vtx = p.VECTOR2I(x, y)
    acute = []
    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            (t1, o1), (t2, o2) = lst[i], lst[j]
            a = (o1.x - x, o1.y - y); c = (o2.x - x, o2.y - y)
            na, nc = math.hypot(*a), math.hypot(*c)
            if na == 0 or nc == 0:
                continue
            ang = math.degrees(math.acos(max(-1, min(1, (a[0] * c[0] + a[1] * c[1]) / na / nc))))
            if 1 <= ang < 89:
                acute.append((ang, t1, o1, t2, o2, na, nc))
    if not acute:
        continue
    where = (b.GetLayerName(L), lst[0][0].GetNetname(), round(tomm(x), 2), round(tomm(y), 2))
    if len(lst) != 2 or occupied(L, n, vtx):
        other.append(where + (round(acute[0][0]),))
        continue
    ang, t1, o1, t2, o2, na, nc = acute[0]
    if t1.m_Uuid.AsString() in used or t2.m_Uuid.AsString() in used:
        skipped.append(where + (round(ang), "segmento gia smussato all'altro capo"))
        continue
    w = min(t1.GetWidth(), t2.GetWidth())
    fix = None
    for d in (0.30, 0.25, 0.20, 0.15, 0.12, 0.10, 0.08):
        dd = min(mm(d), int(0.45 * min(na, nc)))
        p1 = p.VECTOR2I(int(x + (o1.x - x) * dd / na), int(y + (o1.y - y) * dd / na))
        p2 = p.VECTOR2I(int(x + (o2.x - x) * dd / nc), int(y + (o2.y - y) * dd / nc))
        if chord_ok(L, n, p1, p2, w):
            fix = (p1, p2, tomm(dd))
            break
    if not fix:
        skipped.append(where + (round(ang), "nessuno spazio"))
        continue
    used.update({t1.m_Uuid.AsString(), t2.m_Uuid.AsString()})
    done.append(where + (round(ang), round(fix[2], 2)))
    if APPLY:
        for t, pn in ((t1, fix[0]), (t2, fix[1])):
            if t.GetStart() == vtx:
                t.SetStart(pn)
            else:
                t.SetEnd(pn)
        nt = p.PCB_TRACK(b)
        nt.SetStart(fix[0]); nt.SetEnd(fix[1]); nt.SetWidth(w); nt.SetLayer(L); nt.SetNetCode(n)
        b.Add(nt)

print(f"angoli acuti smussati: {len(done)}")
for r in sorted(done):
    print("   ", r)
print(f"non smussati: {len(skipped)}", sorted(skipped))
print(f"acuti con pad/via nel vertice o 3+ piste (non toccati): {len(other)}", sorted(other))
if APPLY and done:
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(path, b)
    print("salvato")
