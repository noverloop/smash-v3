"""Chiude i collegamenti corti rimasti su fin_ble_board. API pcbnew KiCad 10.

Per ogni collegamento aperto (dal rapporto DRC json) delle net indicate:
- net con piano (FLEX_GND, 3V3, COMP_5V_RAW): il gruppo che non tocca il piano cerca, sul suo strato
  esterno, la posizione valida piu vicina per una via passante 0.45/0.20 (o rame della stessa net gia
  sul piano) e ci arriva con una pista corta
- net di segnale: stesso primo tratto fino a una via, poi un secondo tratto sullo strato dove l'altro
  gruppo ha rame, fino a raggiungerlo
Regole NCAB/FAB: pista-rame 0.10, via-pista 0.15, via-via 0.25, foro-foro 0.25, rame-foro 0.20,
bordo 0.30; niente via sotto il corpo del BGA ne dentro le piazzole.
Uso: python.exe close_gaps.py <board.kicad_pcb> <drc.json> [--apply] [NET ...]
"""
import sys, json, re, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path, drcp = sys.argv[1], sys.argv[2]
APPLY = "--apply" in sys.argv
NETS = [a for a in sys.argv[3:] if not a.startswith("--")] or ["FLEX_GND", "3V3", "COMP_5V_RAW", "FIN_HALL", "G0B1_FIN_NRST"]
VD, VH = 0.45, 0.20
G = 0.05
WIN = float(__import__("os").environ.get("WIN","5.0"))
R_EDGE = 17.0 - 0.30 - VD / 2
BGA = (-3.75, 8.75, 2.5 + VD / 2 + 0.05)          # centro e meta lato vietato alle via

b = p.LoadBoard(path)
p.ZONE_FILLER(b).Fill(b.Zones())
b.BuildConnectivity()
C = b.GetConnectivity()
CU = [l for l in b.GetEnabledLayers().Seq() if p.IsCopperLayer(l)]
PLANE_NETS = {z.GetNetname() for z in b.Zones() if not z.GetIsRuleArea()}


def seg_d(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def pad_d(px, py, q):
    x, y, hx, hy, rnd = q
    if rnd:
        return math.hypot(px - x, py - y) - hx
    return math.hypot(max(abs(px - x) - hx, 0), max(abs(py - y) - hy, 0))


def geom():
    """rame per strato: pad, piste, via (con net)"""
    pads, trk, via = [], [], []
    for f in b.GetFootprints():
        for q in f.Pads():
            bb = q.GetBoundingBox()
            rec = (tomm(q.GetPosition().x), tomm(q.GetPosition().y),
                   (tomm(bb.GetRight()) - tomm(bb.GetLeft())) / 2, (tomm(bb.GetBottom()) - tomm(bb.GetTop())) / 2,
                   q.GetShape() == p.PAD_SHAPE_CIRCLE)
            hole = q.GetDrillSize().x > 0
            layers = CU if hole else [l for l in CU if q.IsOnLayer(l)]
            pads.append((rec, q.GetNetname(), layers, hole))
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            via.append((tomm(t.GetPosition().x), tomm(t.GetPosition().y), tomm(t.GetWidth(p.F_Cu)) / 2,
                        tomm(t.GetDrill()) / 2, t.GetNetname(), [l for l in CU if t.IsOnLayer(l)]))
        else:
            trk.append((tomm(t.GetStart().x), tomm(t.GetStart().y), tomm(t.GetEnd().x), tomm(t.GetEnd().y),
                        tomm(t.GetWidth()) / 2, t.GetNetname(), t.GetLayer()))
    return pads, trk, via


def via_ok(x, y, net, G3):
    pads, trk, via = G3
    if math.hypot(x, y) > R_EDGE:
        return False
    if abs(x - BGA[0]) < BGA[2] and abs(y - BGA[1]) < BGA[2]:
        return False
    for rec, n, layers, hole in pads:
        d = pad_d(x, y, rec)
        if n == net and n:
            if d < VD / 2 + 0.05:                       # niente via dentro le piazzole della net
                return False
        elif d < VD / 2 + 0.10 or d < VH / 2 + 0.20:
            return False
        if hole and d < VH / 2 + 0.25:
            return False
    for ax, ay, bx, by, hw, n, lay in trk:
        if n != net and seg_d(x, y, ax, ay, bx, by) < VD / 2 + hw + 0.15:
            return False
    for vx, vy, vr, vh, n, lays in via:
        d = math.hypot(x - vx, y - vy)
        if d < VH / 2 + vh + 0.25:                      # foro-foro, qualunque net
            return False
        if n != net and d < VD / 2 + vr + 0.25:
            return False
    return True


def grid(cx, cy):
    n = int(WIN / G)
    return cx - n * G, cy - n * G, 2 * n + 1


def route_layer(layer, net, starts, goal_fn, hw, G3, x0, y0, size):
    """BFS sullo strato: parte dalle celle 'starts', si ferma dove goal_fn(i,j,x,y) e vero"""
    pads, trk, via = G3
    blk = bytearray(size * size)

    def stamp(fn, bx0, by0, bx1, by1):
        i0 = max(0, int((bx0 - x0) / G)); i1 = min(size - 1, int((bx1 - x0) / G) + 1)
        j0 = max(0, int((by0 - y0) / G)); j1 = min(size - 1, int((by1 - y0) / G) + 1)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if fn(x0 + i * G, y0 + j * G):
                    blk[i * size + j] = 1
    for rec, n, layers, hole in pads:
        if layer in layers and not (n == net and n):
            L = hw + 0.10 + max(rec[2], rec[3])
            stamp(lambda x, y, r=rec: pad_d(x, y, r) < hw + 0.10, rec[0] - L, rec[1] - L, rec[0] + L, rec[1] + L)
    for ax, ay, bx, by, thw, n, lay in trk:
        if lay == layer and n != net:
            L = hw + 0.10 + thw
            stamp(lambda x, y, s=(ax, ay, bx, by, thw): seg_d(x, y, *s[:4]) < hw + 0.10 + s[4],
                  min(ax, bx) - L, min(ay, by) - L, max(ax, bx) + L, max(ay, by) + L)
    for vx, vy, vr, vh, n, lays in via:
        if layer in lays and n != net:
            L = hw + 0.15 + vr
            stamp(lambda x, y, v=(vx, vy), L=L: math.hypot(x - v[0], y - v[1]) < L, vx - L, vy - L, vx + L, vy + L)
    prev = {}
    dq = collections.deque()
    for k in starts:
        if 0 <= k < size * size:
            prev[k] = -1
            dq.append(k)
    while dq:
        k = dq.popleft()
        i, j = divmod(k, size)
        x, y = x0 + i * G, y0 + j * G
        if prev[k] != -1 and goal_fn(i, j, x, y):
            path = []
            while k != -1:
                i, j = divmod(k, size)
                path.append((x0 + i * G, y0 + j * G))
                k = prev[k]
            path.reverse()
            s = [path[0]]
            for m in range(1, len(path) - 1):
                a, c, d = s[-1], path[m], path[m + 1]
                if abs((c[0] - a[0]) * (d[1] - a[1]) - (c[1] - a[1]) * (d[0] - a[0])) > 1e-9:
                    s.append(c)
            s.append(path[-1])
            return s
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            a, c = i + di, j + dj
            if not (0 <= a < size and 0 <= c < size):
                continue
            kk = a * size + c
            if kk in prev or blk[kk]:
                continue
            if di and dj and (blk[a * size + j] or blk[i * size + c]):
                continue
            prev[kk] = k
            dq.append(kk)
    if "--debug" in sys.argv:
        free = sum(1 for k in starts if 0 <= k < size * size and not blk[k])
        print("       celle esplorate %d su %d (partenze libere %d)" % (len(prev), size * size, free))
    return None


def cluster_cells(items, layer, x0, y0, size):
    """celle coperte dal rame del gruppo su 'layer' (punti di partenza o di arrivo)"""
    cells = set()

    def add_rect(ax, ay, bx, by, test):
        for i in range(max(0, int((ax - x0) / G)), min(size - 1, int((bx - x0) / G) + 1) + 1):
            for j in range(max(0, int((ay - y0) / G)), min(size - 1, int((by - y0) / G) + 1) + 1):
                if test(x0 + i * G, y0 + j * G):
                    cells.add(i * size + j)
    for it in items:
        cls = it.GetClass()
        if cls == "PAD" and it.IsOnLayer(layer):
            bb = it.GetBoundingBox()
            rec = (tomm(it.GetPosition().x), tomm(it.GetPosition().y), (tomm(bb.GetRight()) - tomm(bb.GetLeft())) / 2,
                   (tomm(bb.GetBottom()) - tomm(bb.GetTop())) / 2, it.GetShape() == p.PAD_SHAPE_CIRCLE)
            if rec[4]:
                inside = lambda x, y, r=rec: math.hypot(x - r[0], y - r[1]) <= r[2] - 0.02
            else:
                inside = lambda x, y, r=rec: abs(x - r[0]) <= r[2] - 0.02 and abs(y - r[1]) <= r[3] - 0.02
            add_rect(rec[0] - rec[2], rec[1] - rec[3], rec[0] + rec[2], rec[1] + rec[3], inside)
        elif cls == "PCB_TRACK" and it.GetLayer() == layer:
            ax, ay, bx, by = tomm(it.GetStart().x), tomm(it.GetStart().y), tomm(it.GetEnd().x), tomm(it.GetEnd().y)
            w = tomm(it.GetWidth()) / 2
            add_rect(min(ax, bx) - w, min(ay, by) - w, max(ax, bx) + w, max(ay, by) + w,
                     lambda x, y, s=(ax, ay, bx, by), w=w: seg_d(x, y, *s) <= max(w * 0.5, G * 0.75))
        elif cls == "PCB_VIA" and it.IsOnLayer(layer):
            vx, vy = tomm(it.GetPosition().x), tomm(it.GetPosition().y)
            add_rect(vx - 0.1, vy - 0.1, vx + 0.1, vy + 0.1, lambda x, y, v=(vx, vy): math.hypot(x - v[0], y - v[1]) <= 0.1)
    return cells


def find_item(desc, pos):
    """oggetto della scheda descritto dal rapporto DRC nella posizione data"""
    x, y = pos
    P = p.VECTOR2I(mm(x), mm(y))
    net = re.search(r"\[([^\]]+)\]", desc).group(1)
    if desc.startswith("Piazzola"):
        for f in b.GetFootprints():
            for q in f.Pads():
                if q.GetNetname() == net and q.HitTest(P):
                    return q
    for t in b.GetTracks():
        if t.GetNetname() == net and t.HitTest(P):
            return t
    best = None
    for t in b.GetTracks():
        if t.GetNetname() != net:
            continue
        d = math.hypot(tomm(t.GetPosition().x) - x, tomm(t.GetPosition().y) - y)
        if best is None or d < best[0]:
            best = (d, t)
    return best[1] if best else None


def label(it):
    if it.GetClass() == "PAD":
        return it.GetParentFootprint().GetReference() + "." + it.GetNumber()
    return "%s su %s" % (it.GetClass().replace("PCB_", "").lower(), b.GetLayerName(it.GetLayer()))


drc = json.load(open(drcp, encoding="utf8"))
todo = []
for v in drc["unconnected_items"]:
    a, c = v["items"]
    net = re.search(r"\[([^\]]+)\]", a["description"]).group(1)
    if net in NETS:
        mid = ((a["pos"]["x"] + c["pos"]["x"]) / 2, (a["pos"]["y"] + c["pos"]["y"]) / 2)
        todo.append((net, find_item(a["description"], (a["pos"]["x"], a["pos"]["y"])),
                     find_item(c["description"], (c["pos"]["x"], c["pos"]["y"])), mid))

PLANE_LAYERS = {z.GetFirstLayer() for z in b.Zones() if not z.GetIsRuleArea()}
EXTRA = [b.GetLayerID(n) for n in __import__("os").environ.get("EXTRA_LAYERS", "").split(",") if n]
SIG = [l for l in CU if l not in PLANE_LAYERS or l in EXTRA]   # EXTRA_LAYERS: piani usabili anche per piste


def on_plane_items(net):
    """rame della net gia collegato a un piano (via, piste, pad)"""
    out = []
    for z in b.Zones():
        if z.GetNetname() == net and not z.GetIsRuleArea():
            out += [it for it in C.GetConnectedItems(z) if it.GetClass() != "ZONE"]
    return out

G3 = geom()
new_trk, new_via, done, fail = [], [], [], []
handled = set()
for net, A, B, mid in todo:
    conn_a = C.GetConnectedItems(A)
    conn_b = C.GetConnectedItems(B)
    if B.m_Uuid.AsString() in {it.m_Uuid.AsString() for it in conn_a}:
        print("  %-14s gia collegato" % net)
        continue
    on_a = any(it.GetClass() == "ZONE" for it in conn_a)
    on_b = any(it.GetClass() == "ZONE" for it in conn_b)
    power = net in PLANE_NETS
    if power and on_a and on_b:
        print("  %-14s entrambi i gruppi risultano sul piano: da verificare a mano" % net)
        fail.append(net)
        continue
    if power and on_a and not on_b:
        A, B, conn_a, conn_b = B, A, conn_b, conn_a
    if power:                                           # stesso gruppo elencato piu volte dalla DRC
        key = min([A.m_Uuid.AsString()] + [it.m_Uuid.AsString() for it in conn_a if it.GetClass() != "ZONE"])
        if key in handled:
            print("  %-14s gruppo di %s gia trattato" % (net, label(A)))
            continue
        handled.add(key)
    x0, y0, size = grid(*mid)
    hw = 0.10 if power else 0.05
    ok = False
    # i segnali provano a partire da entrambi i capi
    orders = [(A, B, conn_a, conn_b)] if power else [(A, B, conn_a, conn_b), (B, A, conn_b, conn_a)]
    attempts = []
    for A_, B_, ca_, cb_ in orders:
        ia = [A_] + [it for it in ca_ if it.GetClass() != "ZONE"]
        ib = [B_] + [it for it in cb_ if it.GetClass() != "ZONE"]
        if power:                                       # qualunque rame della net gia sul piano va bene
            ida = {it.m_Uuid.AsString() for it in ia}
            ib = [it for it in on_plane_items(net) if it.m_Uuid.AsString() not in ida]
        attempts += [(A_, ia, ib, L) for L in SIG]
    for A, items_a, items_b, L1 in attempts:
        if ok:
            break
        starts = cluster_cells(items_a, L1, x0, y0, size)
        if not starts:
            continue
        goal_b = cluster_cells(items_b, L1, x0, y0, size)
        if "--debug" in sys.argv:
            print("     [%s su %s] partenze %d, arrivi %d, oggetti gruppo A %d, gruppo B %d" % (
                net, b.GetLayerName(L1), len(starts), len(goal_b), len(items_a), len(items_b)))
        p1 = route_layer(L1, net, starts,
                         lambda i, j, x, y: (i * size + j) in goal_b or via_ok(x, y, net, G3),
                         hw, G3, x0, y0, size)
        if not p1:
            continue
        ex, ey = p1[-1]
        ek = int(round((ex - x0) / G)) * size + int(round((ey - y0) / G))
        legs, vias = [(L1, p1)], []
        if ek not in goal_b:
            vias.append((ex, ey))
            if not power:                               # secondo tratto verso l'altro gruppo
                p2 = None
                for L2 in SIG:
                    gb = cluster_cells(items_b, L2, x0, y0, size)
                    if not gb:
                        continue
                    p2 = route_layer(L2, net, {ek}, lambda i, j, x, y, gb=gb: (i * size + j) in gb,
                                     0.05, G3, x0, y0, size)
                    if p2:
                        legs.append((L2, p2))
                        break
                if not p2:
                    continue
        for L, s in legs:
            w = hw * 2 if L == L1 else 0.10
            for a2, c2 in zip(s, s[1:]):
                new_trk.append((a2, c2, L, net, w))
                G3[1].append((a2[0], a2[1], c2[0], c2[1], w / 2, net, L))
        for vx, vy in vias:
            new_via.append((vx, vy, net))
            G3[2].append((vx, vy, VD / 2, VH / 2, net, CU))
        Ltot = sum(math.hypot(c2[0] - a2[0], c2[1] - a2[1]) for _, s in legs for a2, c2 in zip(s, s[1:]))
        done.append(net)
        print("  %-14s da %-24s -> %s, piste %.2f mm%s" % (
            net, label(A), "via (%.2f,%.2f)" % vias[0] if vias else "rame della net", Ltot,
            " + tratto su " + b.GetLayerName(legs[-1][0]) if len(legs) > 1 else ""))
        ok = True
        break
    if not ok:
        fail.append(net)
        print("  %-14s da %-24s NESSUN PERCORSO entro %.0f mm" % (net, label(A), WIN))
print("\nchiusi %d, non riusciti %d" % (len(done), len(fail)))

if APPLY and done:
    for a2, c2, L, net, w in new_trk:
        t = p.PCB_TRACK(b); b.Add(t)
        t.SetStart(p.VECTOR2I(mm(a2[0]), mm(a2[1]))); t.SetEnd(p.VECTOR2I(mm(c2[0]), mm(c2[1])))
        t.SetWidth(mm(w)); t.SetLayer(L); t.SetNet(b.FindNet(net))
    for vx, vy, net in new_via:
        v = p.PCB_VIA(b); b.Add(v)
        v.SetPosition(p.VECTOR2I(mm(vx), mm(vy))); v.SetViaType(p.VIATYPE_THROUGH)
        v.SetLayerPair(p.F_Cu, p.B_Cu); v.SetWidth(mm(VD)); v.SetDrill(mm(VH)); v.SetNet(b.FindNet(net))
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(path, b)
    print("salvato")
