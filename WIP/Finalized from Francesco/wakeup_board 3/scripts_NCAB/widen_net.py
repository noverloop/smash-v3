"""wakeup_board - review Sjoert: piste di potenza troppo sottili (REG_IN_MAIN).

Allarga ogni segmento della net alla larghezza massima possibile (passi di 0.05 mm, fino a WMAX),
senza mai restringerlo, rispettando: piste/pad di altre net 0.10, via passanti 0.15 (FAB),
microvia 0.10, bordo scheda 0.30. Le gocce (teardrop) dei segmenti cambiati vanno rigenerate
da KiCad (Modifica -> Modifica lacrime).
Uso: python.exe widen_net.py <board.kicad_pcb> <NET> [WMAX] [--apply]
"""
import sys, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path, NET = sys.argv[1], sys.argv[2]
WMAX = float(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else 0.4
APPLY = "--apply" in sys.argv
C_CU, C_VT, C_EDGE = 0.10, 0.15, 0.30
b = p.LoadBoard(path)
T = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
V = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
P = [(f, q) for f in b.GetFootprints() for q in f.Pads()]
edge = [d for d in b.GetDrawings() if d.GetLayer() == p.Edge_Cuts]


def fits(t, w):
    L = t.GetLayer()
    seg = p.SHAPE_SEGMENT(t.GetStart(), t.GetEnd(), mm(w))
    for o in T:
        if o.GetNetname() != NET and o.GetLayer() == L and o.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for f, q in P:
        if q.GetNetname() != NET and q.IsOnLayer(L) and q.GetEffectiveShape(L).Collide(seg, mm(C_CU)):
            return False
    for v in V:
        if v.GetNetname() != NET and v.IsOnLayer(L):
            thr = v.GetViaType() == p.VIATYPE_THROUGH
            if seg.Collide(p.SHAPE_CIRCLE(v.GetPosition(), v.GetWidth(L) // 2), mm(C_VT if thr else C_CU)):
                return False
    for d in edge:
        if d.GetEffectiveShape().Collide(seg, mm(C_EDGE)):
            return False
    return True


changes = []
for t in T:
    if t.GetNetname() != NET:
        continue
    w0 = round(tomm(t.GetWidth()), 4)
    best = None
    w = WMAX
    while w > w0 + 1e-6:
        if fits(t, w):
            best = w
            break
        w = round(w - 0.05, 3)
    if best:
        changes.append((t, w0, best))

hist = collections.Counter((b.GetLayerName(t.GetLayer()), w0, w1) for t, w0, w1 in changes)
print(f"{NET}: segmenti {sum(1 for t in T if t.GetNetname() == NET)}, allargati {len(changes)}")
for (L, w0, w1), n in sorted(hist.items()):
    print(f"  {L:6s} {w0:.3f} -> {w1:.2f} mm  x{n}")
left = [(b.GetLayerName(t.GetLayer()), round(tomm(t.GetWidth()), 3), round(tomm(t.GetLength()), 2),
         round(tomm(t.GetStart().x), 2), round(tomm(t.GetStart().y), 2))
        for t in T if t.GetNetname() == NET and t not in [c[0] for c in changes] and tomm(t.GetWidth()) < 0.2 - 1e-3]
print("restano sotto 0.2 mm (nessuno spazio):", left)

if APPLY and changes:
    for t, w0, w1 in changes:
        t.SetWidth(mm(w1))
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(path, b)
    print("salvato")
