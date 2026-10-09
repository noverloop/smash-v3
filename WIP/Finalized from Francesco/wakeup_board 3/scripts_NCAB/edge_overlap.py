"""wakeup_board - review Sjoert: bordo scheda ad arco vero + piste sovrapposte.

1. Edge.Cuts: i 90 segmenti (corde di un cerchio R17 centrato in 0,0) diventano un unico cerchio
   R17 con lo stesso spessore. Se un vertice non sta sul cerchio non tocca niente.
2. Piste sovrapposte: dove due segmenti della stessa net e dello stesso strato partono dallo stesso
   punto nella stessa direzione, il piu corto e contenuto nel piu lungo: viene tolto (se non e piu
   largo). 3. Pezzetti con un capo libero piu corti di 0.3 mm: tolti solo quelli che la DRC di
   KiCad segnala come track_dangling (report JSON di kicad-cli passato con --dangling).
Uso: python.exe edge_overlap.py <board.kicad_pcb> [--dangling drc.json]
"""
import sys, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
b = p.LoadBoard(path)
R = 17.0

# ---- 1. bordo
E = [d for d in b.GetDrawings() if d.GetLayer() == p.Edge_Cuts]
ok = E and all(d.GetShapeStr() == "Line" for d in E) and all(
    abs(math.hypot(tomm(q.x), tomm(q.y)) - R) < 0.001 for d in E for q in (d.GetStart(), d.GetEnd()))
if ok:
    w = E[0].GetWidth()
    for d in E:
        b.Remove(d)
    c = p.PCB_SHAPE(b, p.SHAPE_T_CIRCLE)
    c.SetLayer(p.Edge_Cuts)
    c.SetCenter(p.VECTOR2I(0, 0))
    c.SetEnd(p.VECTOR2I(mm(R), 0))
    c.SetWidth(w)
    b.Add(c)
    print(f"Edge.Cuts: {len(E)} segmenti -> cerchio R{R}")
else:
    print("Edge.Cuts: non e un cerchio R17 a segmenti, lasciato com'e")

# ---- 2. piste sovrapposte
T = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
ends = collections.defaultdict(list)
for t in T:
    for a, o in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
        ends[(t.GetLayer(), t.GetNetCode(), a.x, a.y)].append((t, o.x - a.x, o.y - a.y))
gone = {}
for k, lst in ends.items():
    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            (t1, x1, y1), (t2, x2, y2) = lst[i], lst[j]
            n1, n2 = math.hypot(x1, y1), math.hypot(x2, y2)
            if n1 == 0 or n2 == 0:
                continue
            if (x1 * x2 + y1 * y2) / n1 / n2 < math.cos(math.radians(1)):
                continue
            short, long_ = (t1, t2) if n1 <= n2 else (t2, t1)
            if short.GetWidth() <= long_.GetWidth():
                gone[short.m_Uuid.AsString()] = short
print("piste sovrapposte tolte:", len(gone),
      dict(collections.Counter(f"{t.GetNetname()}@{b.GetLayerName(t.GetLayer())}" for t in gone.values())))
for t in gone.values():
    b.Remove(t)

# ---- 3. pezzetti con un capo libero (< 0.3 mm) segnalati dalla DRC
if "--dangling" in sys.argv:
    import json
    drc = json.load(open(sys.argv[sys.argv.index("--dangling") + 1], encoding="utf8"))
    ids = {i["uuid"] for v in drc["violations"] if v["type"] == "track_dangling" for i in v["items"]}
    stub = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.m_Uuid.AsString() in ids
            and tomm(t.GetLength()) < 0.3]
    print("pezzetti pendenti tolti:", [(t.GetNetname(), b.GetLayerName(t.GetLayer()), round(tomm(t.GetLength()), 3)) for t in stub])
    for t in stub:
        b.Remove(t)

p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)
print("salvato")
