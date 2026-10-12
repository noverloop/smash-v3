"""Chiude i collegamenti verso i piani con un router a griglia.
Per ogni pad ancora scollegato di una net con piano cerca, entro 6 mm, un percorso libero
sul proprio layer fino a un punto dove si puo mettere un via passante 0.45/0.20.
Griglia 0.05 mm, spostamenti a 90 e 45 gradi, ostacoli gonfiati delle distanze richieste:
0.10 dal rame di altre net, 0.15 via-pista, 0.25 via-via, 0.20 rame-foro, 0.45 foro-foro,
0.30 dal bordo. Per le net di In9 il via deve cadere nella regione della propria net.
Uso: python.exe maze_vias.py <board.kicad_pcb> <drc.json> [--apply] [raggio_mm]
"""
import sys, json, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
bp, dp = sys.argv[1], sys.argv[2]
APPLY = "--apply" in sys.argv
args = [a for a in sys.argv[3:] if not a.startswith("--")]
MAXR = float(args[0]) if args else 6.0
NETS = ["FLEX_GND", "3V3", "COMP_5V_RAW"]
VIA_D, VIA_H, TW = 0.45, 0.20, 0.10
G = 0.05                      # passo griglia
R_EDGE = 17.0 - 0.30 - VIA_D / 2

b = p.LoadBoard(bp)
drc = json.load(open(dp, encoding="utf8"))
new_vias = []                 # (x, y, net) dei via aggiunti in questa esecuzione
added_segs = []               # (x1, y1, x2, y2, hw, layer, net) piste aggiunte

def collect(net):
    """ostacoli di altre net: pad (rettangoli con layer), piste, via"""
    pads, segs, vias = [], [], []
    for (x1, y1, x2, y2, hw, lay, nn) in added_segs:
        if nn != net: segs.append((x1, y1, x2, y2, hw, lay))
    for f in b.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname() == net: continue
            bb = pd.GetBoundingBox(); seq = pd.GetLayerSet().Seq()
            pads.append((tomm(bb.GetLeft()), tomm(bb.GetTop()), tomm(bb.GetRight()), tomm(bb.GetBottom()),
                         seq[0] if seq else p.F_Cu))
    for t in b.GetTracks():
        if t.GetNetname() == net:
            if t.GetClass() == "PCB_VIA":
                vias.append((tomm(t.GetPosition().x), tomm(t.GetPosition().y),
                             tomm(t.GetWidth(p.F_Cu)) / 2, True))
            continue
        if t.GetClass() == "PCB_VIA":
            vias.append((tomm(t.GetPosition().x), tomm(t.GetPosition().y),
                         tomm(t.GetWidth(p.F_Cu)) / 2, False))
        else:
            segs.append((tomm(t.GetStart().x), tomm(t.GetStart().y), tomm(t.GetEnd().x), tomm(t.GetEnd().y),
                         tomm(t.GetWidth()) / 2, t.GetLayer()))
    return pads, segs, vias

def route_pad(px, py, layer, pads, segs, vias, zs, split, pad_half, net):
    n = int(MAXR / G)
    def ij2xy(i, j): return px + (i - n) * G, py + (j - n) * G
    size = 2 * n + 1
    blocked = bytearray(size * size)        # cella non percorribile dalla pista
    viaok = bytearray(size * size)          # cella dove si puo mettere il via

    def stamp(cx, cy, r_track, r_via):
        i0 = max(0, int((cx - r_via - px) / G) + n - 1); i1 = min(size - 1, int((cx + r_via - px) / G) + n + 1)
        j0 = max(0, int((cy - r_via - py) / G) + n - 1); j1 = min(size - 1, int((cy + r_via - py) / G) + n + 1)
        for i in range(i0, i1 + 1):
            x = px + (i - n) * G
            for j in range(j0, j1 + 1):
                y = py + (j - n) * G
                d = math.hypot(x - cx, y - cy)
                k = i * size + j
                if d < r_track: blocked[k] = 1
                if d < r_via: viaok[k] = 1      # 1 = vietato, si inverte dopo

    for (x0, y0, x1, y1, lay) in pads:
        # rettangolo: si campiona la distanza cella per cella nell'intorno
        i0 = max(0, int((x0 - 0.6 - px) / G) + n); i1 = min(size - 1, int((x1 + 0.6 - px) / G) + n)
        j0 = max(0, int((y0 - 0.6 - py) / G) + n); j1 = min(size - 1, int((y1 + 0.6 - py) / G) + n)
        for i in range(i0, i1 + 1):
            x = px + (i - n) * G
            dx = max(x0 - x, 0, x - x1)
            for j in range(j0, j1 + 1):
                y = py + (j - n) * G
                d = math.hypot(dx, max(y0 - y, 0, y - y1))
                k = i * size + j
                if lay == layer and d < TW / 2 + 0.10: blocked[k] = 1
                if d < VIA_D / 2 + 0.10 or d < VIA_H / 2 + 0.20: viaok[k] = 1
    for (x1, y1, x2, y2, hw, lay) in segs:
        steps = max(2, int(math.hypot(x2 - x1, y2 - y1) / G))
        for s in range(steps + 1):
            cx = x1 + (x2 - x1) * s / steps; cy = y1 + (y2 - y1) * s / steps
            if abs(cx - px) > MAXR + 1 or abs(cy - py) > MAXR + 1: continue
            stamp(cx, cy, (TW / 2 + hw + 0.10) if lay == layer else 0, VIA_D / 2 + hw + 0.15)
    for (cx, cy, vr, same) in vias:
        if abs(cx - px) > MAXR + 1 or abs(cy - py) > MAXR + 1: continue
        if same:
            stamp(cx, cy, 0, VIA_H + 0.25)                    # foro-foro tra via della stessa net
        else:
            stamp(cx, cy, vr + TW / 2 + 0.15, VIA_D / 2 + vr + 0.25)

    # inverte viaok (1 = vietato -> ok) e applica bordo scheda e zona
    for k in range(size * size):
        i, j = divmod(k, size)
        x, y = ij2xy(i, j)
        ok = not viaok[k] and math.hypot(x, y) <= R_EDGE
        if ok and split:
            ok = any(z.HitTestFilledArea(z.GetFirstLayer(), p.VECTOR2I(mm(x), mm(y)), 0) for z in zs)
        viaok[k] = 1 if ok else 0

    # BFS dal pad
    start = (n, n)
    prev = {start: None}
    q = collections.deque([start])
    goal = None
    minr = pad_half + VIA_D / 2 + 0.10
    while q:
        i, j = q.popleft()
        x, y = ij2xy(i, j)
        if viaok[i * size + j] and math.hypot(x - px, y - py) >= minr:
            goal = (i, j); break
        for di, dj in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < size and 0 <= nj < size): continue
            if (ni, nj) in prev: continue
            if blocked[ni * size + nj] and math.hypot((ni-n)*G, (nj-n)*G) > pad_half: continue
            prev[(ni, nj)] = (i, j); q.append((ni, nj))
    if goal is None: return None
    path = []
    cur = goal
    while cur is not None:
        path.append(ij2xy(*cur)); cur = prev[cur]
    path.reverse()
    # semplifica i tratti allineati
    simp = [path[0]]
    for k in range(1, len(path) - 1):
        a, c, d = simp[-1], path[k], path[k + 1]
        if abs((c[0]-a[0])*(d[1]-a[1]) - (c[1]-a[1])*(d[0]-a[0])) > 1e-9: simp.append(c)
    simp.append(path[-1])
    return simp

made, failed = [], []
for NET in NETS:
    zs = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == NET]
    if not zs: continue
    split = all(z.GetFirstLayer() == p.In9_Cu for z in zs)
    want = set()
    for v in drc.get("unconnected_items", []):
        for i in v["items"]:
            if "Piazzola" in i["description"] and f"[{NET}]" in i["description"]:
                want.add((round(i["pos"]["x"], 3), round(i["pos"]["y"], 3)))
    pads_todo = []
    for f in b.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname() != NET: continue
            if (round(tomm(pd.GetPosition().x), 3), round(tomm(pd.GetPosition().y), 3)) in want:
                pads_todo.append((f, pd))
    if not pads_todo: continue
    ok = ko = 0
    for f, pd in pads_todo:
        px, py = tomm(pd.GetPosition().x), tomm(pd.GetPosition().y)
        bb = pd.GetBoundingBox()
        half = math.hypot(tomm(bb.GetRight()) - tomm(bb.GetLeft()), tomm(bb.GetBottom()) - tomm(bb.GetTop())) / 2
        seq = pd.GetLayerSet().Seq(); layer = seq[0] if seq else p.F_Cu
        obst = collect(NET)
        obst[2].extend([(vx, vy, VIA_D / 2, vn == NET) for vx, vy, vn in new_vias])
        path = route_pad(px, py, layer, *obst, zs, split, half, NET)
        if path:
            new_vias.append((path[-1][0], path[-1][1], NET))
            for a, c in zip(path, path[1:]):
                added_segs.append((a[0], a[1], c[0], c[1], TW / 2, layer, NET))
            made.append((NET, path, layer)); ok += 1
        else:
            failed.append((NET, f.GetReference(), pd.GetNumber(), px, py)); ko += 1
    print(f"{NET:12s} da collegare {len(pads_todo):3d} -> riusciti {ok:3d}, falliti {ko:3d}")
print(f"TOTALE riusciti {len(made)}, falliti {len(failed)}")
for r in failed[:10]: print(f"   {r[0]:12s} {r[1]}.{r[2]} ({r[3]:.2f},{r[4]:.2f})")

if APPLY and made:
    for NET, path, layer in made:
        net = b.FindNet(NET)
        for a, c in zip(path, path[1:]):
            t = p.PCB_TRACK(b); b.Add(t)
            t.SetStart(p.VECTOR2I(mm(a[0]), mm(a[1]))); t.SetEnd(p.VECTOR2I(mm(c[0]), mm(c[1])))
            t.SetWidth(mm(TW)); t.SetLayer(layer); t.SetNet(net)
        v = p.PCB_VIA(b); b.Add(v)
        v.SetPosition(p.VECTOR2I(mm(path[-1][0]), mm(path[-1][1])))
        v.SetViaType(p.VIATYPE_THROUGH); v.SetLayerPair(p.F_Cu, p.B_Cu)
        v.SetDrill(mm(VIA_H)); v.SetWidth(mm(VIA_D)); v.SetNet(net)
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(bp, b)
    print("salvato")
else:
    print("(analisi soltanto)")
