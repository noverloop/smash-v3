"""Fanout HDI di U_WBA (STM32WBA55, WLCSP41 passo 0.35 mm) - API pcbnew KiCad 10.

- microvia laser 0.10/0.25 (F.Cu -> In1.Cu) nel pad di ogni sfera interna collegata
- uscite su In1.Cu, larghezza 0.10, su percorsi disgiunti del reticolo delle sfere
  (flusso massimo con capacita 1 sui nodi): distanze >= 0.15 mm per costruzione
- via passante 0.45/0.20 in fondo a ogni uscita, fuori dal campo sfere
Tutto bloccato (locked) per Freerouting.
Uso: python.exe fanout_uwba.py <board.kicad_pcb>
"""
import sys, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
b = p.LoadBoard(path)
fp = b.FindFootprintByReference("U_WBA")
CX, CY = tomm(fp.GetPosition().x), tomm(fp.GetPosition().y)

PX, PY = 0.35, 0.20            # passo reticolo (colonne, righe)
X0, Y0 = -1.05, -1.20          # nodo (0,0) relativo al centro
UV_D, UV_H = 0.25, 0.10        # microvia
V_D, V_H = 0.45, 0.20          # via di fanout
TW = 0.10                      # pista di uscita
VIA_MIN_PITCH = 0.80           # tra via di fanout (i vicini in comune vengono bloccati)
VIA_BALL_MIN = 0.75            # via di fanout <-> centro sfera
PAD_KEEP = 0.33                # centro via <-> bordo pad di altre net (F.Cu/B.Cu)
GND = "FLEX_GND"
SKIP = {"WBA_SWDIO"}           # net con un solo nodo: niente fanout per ora

def node_xy(i, j):
    return X0 + PX * i, Y0 + PY * j

def to_node(x, y):
    return round((x - X0) / PX), round((y - Y0) / PY)

# ---------------------------------------------------------------- sfere
balls = {}
for pd in fp.Pads():
    x, y = tomm(pd.GetPosition().x) - CX, tomm(pd.GetPosition().y) - CY
    ij = to_node(x, y)
    assert abs(node_xy(*ij)[0] - x) < 1e-3 and abs(node_xy(*ij)[1] - y) < 1e-3, pd.GetNumber()
    balls[ij] = (pd.GetNumber(), pd.GetNetname(), pd)

def is_node(i, j):
    return (i + j) % 2 == 1

NB = [(1, 1), (1, -1), (-1, 1), (-1, -1), (0, 2), (0, -2)]

def neighbors(n):
    return [(n[0] + di, n[1] + dj) for di, dj in NB]

BALL_R = 0.1105
RAY_KEEP = BALL_R + 0.10 + 0.05     # raggio sfera + clearance + meta pista 0.10

def perimeter(ij):
    """Sfera esterna = ha un'uscita dritta a 0/45/90 gradi su F.Cu (come Freerouting)."""
    x, y = node_xy(*ij)
    for k in range(8):
        a = math.radians(45 * k)
        dx, dy = math.cos(a), math.sin(a)
        ok = True
        for o in balls:
            if o == ij:
                continue
            ox, oy = node_xy(*o)
            t = (ox - x) * dx + (oy - y) * dy
            if t > 0 and abs((ox - x) * dy - (oy - y) * dx) < RAY_KEEP:
                ok = False
                break
        if ok:
            return True
    return False

interior = {ij for ij in balls if not perimeter(ij)}
sources = {ij: balls[ij][1] for ij in interior if balls[ij][1] and balls[ij][1] != GND and balls[ij][1] not in SKIP}
gnd_uv = {ij for ij in interior if balls[ij][1] == GND}
print(f"sfere interne {len(interior)}: sorgenti {len(sources)}, GND {len(gnd_uv)}")

# ---------------------------------------------------------- ostacoli F/B
def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

pads_fb = []   # (x0,y0,x1,y1,net) bbox assoluti su F.Cu/B.Cu
for f in b.GetFootprints():
    if f.GetReference() == "U_WBA":
        continue
    for pd in f.Pads():
        bb = pd.GetBoundingBox()
        pads_fb.append((tomm(bb.GetLeft()), tomm(bb.GetTop()), tomm(bb.GetRight()), tomm(bb.GetBottom()), pd.GetNetname()))
old_vias = [(tomm(t.GetPosition().x), tomm(t.GetPosition().y), tomm(t.GetWidth(p.F_Cu)) / 2)
            for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
old_trk = [(tomm(t.GetStart().x), tomm(t.GetStart().y), tomm(t.GetEnd().x), tomm(t.GetEnd().y), tomm(t.GetWidth()) / 2, t.GetLayer())
           for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]

def bbox_dist(x, y, bb):
    dx = max(bb[0] - x, 0, x - bb[2])
    dy = max(bb[1] - y, 0, y - bb[3])
    return math.hypot(dx, dy)

# corridoio RF: dalla sfera WBA_RF verso C_WBA_PI1, primi 3 mm
rf_ball = next(ij for ij, v in balls.items() if v[1] == "WBA_RF")
rfx, rfy = node_xy(*rf_ball)
pi1 = b.FindFootprintByReference("C_WBA_PI1")
tx, ty = tomm(pi1.GetPosition().x) - CX, tomm(pi1.GetPosition().y) - CY
L = math.hypot(tx - rfx, ty - rfy)
rf_end = (rfx + (tx - rfx) / L * 3.0, rfy + (ty - rfy) / L * 3.0)

def via_site_ok(n):
    x, y = node_xy(*n)
    ax, ay = x + CX, y + CY
    if n in balls:
        return False
    if min(math.hypot(x - bx, y - by) for bx, by in (node_xy(*ij) for ij in balls)) < VIA_BALL_MIN:
        return False
    if seg_dist(x, y, rfx, rfy, *rf_end) < 1.0:
        return False
    for bb in pads_fb:
        if bbox_dist(ax, ay, bb) < PAD_KEEP:
            return False
    for vx, vy, vr in old_vias:
        if math.hypot(ax - vx, ay - vy) < vr + 0.25 + V_D / 2:
            return False
    for x1, y1, x2, y2, hw, lay in old_trk:
        if lay in (p.F_Cu, p.B_Cu) and seg_dist(ax, ay, x1, y1, x2, y2) < V_D / 2 + 0.15 + hw:
            return False
    if math.hypot(ax, ay) > 17.0 - 0.3 - V_D:        # bordo scheda D34
        return False
    return True

# nodi del reticolo esteso
RI, RJ = range(-11, 18), range(-26, 39)
nodes = [(i, j) for i in RI for j in RJ if is_node(i, j)]
cands = sorted((n for n in nodes if via_site_ok(n)), key=lambda n: math.hypot(*node_xy(*n)))
sites = []
for n in cands:
    x, y = node_xy(*n)
    if all(math.hypot(x - node_xy(*s)[0], y - node_xy(*s)[1]) >= VIA_MIN_PITCH for s in sites):
        sites.append(n)
sites = sites[:60]
site_set = set(sites)
reserved = {}   # vicino di un via -> quel via
shared = set()  # vicino di due via: nessuna pista ci puo passare (via-pista 0.15)
for s in sites:
    for nb in neighbors(s):
        if nb in reserved and reserved[nb] != s:
            shared.add(nb)
        reserved[nb] = s
print(f"siti via candidati: {len(sites)}")

# zona di rispetto RF su In1: il riferimento GND sotto il primo tratto della
# pista WBA_RF (sfera C2 -> C_WBA_PI1) deve restare pieno -> niente uscite qui
RF_KEEP = 0.55
rf_keep = {n for n in nodes if seg_dist(*node_xy(*n), rfx, rfy, *rf_end) < RF_KEEP}

# nodi bloccati su In1: microvia GND, altre sorgenti (gestite a parte), via esistenti su In1
blocked = set(gnd_uv) | shared
for n in nodes:
    x, y = node_xy(*n)
    for vx, vy, vr in old_vias:
        if math.hypot(x + CX - vx, y + CY - vy) < vr + 0.15 + TW / 2 + 0.2:
            blocked.add(n)

# ------------------------------ corridoi di massa: le microvia GND devono restare
# collegate al piano In1 esterno. Microvia GND adiacenti formano un gruppo con un
# solo corridoio; per ogni gruppo si provano corridoi verso direzioni diverse.
import itertools
nodeset = set(nodes)
ball_xy = [node_xy(*ij) for ij in balls]
def outside(n):
    x, y = node_xy(*n)
    return min(math.hypot(x - bx, y - by) for bx, by in ball_xy) >= 0.5

groups, seen = [], set()
for g in sorted(gnd_uv):
    if g in seen:
        continue
    comp, stack = set(), [g]
    while stack:
        u = stack.pop()
        if u in comp:
            continue
        comp.add(u)
        stack += [nb for nb in neighbors(u) if nb in gnd_uv]
    seen |= comp
    groups.append(comp)

def corridors(comp):
    """Un corridoio minimo per ciascuno degli 8 settori di uscita."""
    best = {}
    prev = {u: None for u in comp}
    q = collections.deque(comp)
    while q:
        u = q.popleft()
        if outside(u):
            x, y = node_xy(*u)
            sec = int(((math.degrees(math.atan2(y, x)) + 360) % 360) // 45)
            if sec not in best:
                seq, w = [], u
                while w is not None:
                    seq.append(w)
                    w = prev[w]
                seq.reverse()                      # dal nodo GND verso l'esterno
                best[sec] = (frozenset(x for x in seq if x not in comp), tuple(seq))
            continue
        for nb in neighbors(u):
            if nb in prev or nb not in nodeset or nb in sources or nb in site_set or nb in reserved:
                continue
            if nb in blocked:
                continue
            prev[nb] = u
            q.append(nb)
    return sorted(best.values(), key=lambda c: len(c[0]))

S, T = "S", "T"
def run_flow(extra_block):
    blk = blocked | extra_block | rf_keep
    cap = collections.defaultdict(int)
    adj = collections.defaultdict(set)
    def add(u, v):
        cap[(u, v)] += 1
        adj[u].add(v); adj[v].add(u)
    for n in nodes:
        if n in blk:
            continue
        add(("in", n), ("out", n))
        if n in site_set:
            add(("out", n), T)
            continue
        for nb in neighbors(n):
            if nb not in nodeset or nb in blk or nb in sources:
                continue
            if n in reserved and nb != reserved[n]:
                continue            # dal vicino di un via si va solo nel via
            add(("out", n), ("in", nb))
    for s0 in sources:
        add(S, ("in", s0))
    flow = collections.defaultdict(int)
    total = 0
    while True:
        prev = {S: None}
        q = collections.deque([S])
        while q and T not in prev:
            u = q.popleft()
            for v in adj[u]:
                if v not in prev and cap[(u, v)] - flow[(u, v)] > 0:
                    prev[v] = u
                    q.append(v)
        if T not in prev:
            break
        v = T
        while prev[v] is not None:
            u = prev[v]; flow[(u, v)] += 1; flow[(v, u)] -= 1; v = u
        total += 1
    if total < len(sources):
        return None
    res = {}
    for s0 in sources:
        seq, u = [s0], ("in", s0)
        while True:
            u = next(v for v in adj[u] if flow[(u, v)] > 0)
            if u == T:
                break
            if u[0] == "in":
                seq.append(u[1])
        res[s0] = seq
    return res

cand = [corridors(g) for g in groups]
print("gruppi GND:", [sorted(balls[u][0] for u in g) for g in groups], "corridoi candidati:", [len(c) for c in cand])
ok_combos, tried = [], set()
for combo in sorted(itertools.product(*cand), key=lambda c: sum(len(x[0]) for x in c)):
    extra = frozenset().union(*(c[0] for c in combo))
    if extra in tried:
        continue
    tried.add(extra)
    pth = run_flow(extra)
    if pth:
        ok_combos.append((extra, pth, [c[1] for c in combo]))
    if len(ok_combos) >= 30:
        break
if not ok_combos:
    sys.exit("fanout incompleto: niente salvato")
print(f"combinazioni con tutte le {len(sources)} uscite: {len(ok_combos)}")

# ------------------------------------------------------------- creazione
def absxy(n):
    x, y = node_xy(*n)
    return (round(x + CX, 4), round(y + CY, 4))

def build(bd, paths, gnd_paths):
    def add_via(pos, net, vtype, top, bot, d, h):
        v = p.PCB_VIA(bd); bd.Add(v)
        v.SetPosition(p.VECTOR2I(mm(pos[0]), mm(pos[1])))
        v.SetViaType(vtype); v.SetLayerPair(top, bot)
        v.SetDrill(mm(h)); v.SetWidth(mm(d))
        v.SetNet(net); v.SetLocked(True)
    def add_trk(a, c, net):
        t = p.PCB_TRACK(bd); bd.Add(t)
        t.SetStart(p.VECTOR2I(mm(a[0]), mm(a[1]))); t.SetEnd(p.VECTOR2I(mm(c[0]), mm(c[1])))
        t.SetWidth(mm(TW)); t.SetLayer(p.In1_Cu); t.SetNet(net); t.SetLocked(True)
    n_uv = n_trk = 0
    for ij in sorted(interior):
        num, net, pd = balls[ij]
        if not net or net in SKIP:
            continue
        add_via(absxy(ij), bd.FindNet(net), p.VIATYPE_MICROVIA, p.F_Cu, p.In1_Cu, UV_D, UV_H)
        n_uv += 1
    log = []
    for s0, seq in paths.items():
        net = bd.FindNet(sources[s0])
        pts = [absxy(n) for n in seq]
        simp = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, c, d = simp[-1], pts[k], pts[k + 1]
            if abs((c[0] - a[0]) * (d[1] - a[1]) - (c[1] - a[1]) * (d[0] - a[0])) > 1e-6:
                simp.append(c)
        simp.append(pts[-1])
        for a, c in zip(simp, simp[1:]):
            add_trk(a, c, net); n_trk += 1
        add_via(pts[-1], net, p.VIATYPE_THROUGH, p.F_Cu, p.B_Cu, V_D, V_H)
        log.append(f"  {balls[s0][0]:4s} {sources[s0]:14s} {len(seq)-1:2d} passi -> via ({pts[-1][0]:.3f},{pts[-1][1]:.3f})")
    gnet = bd.FindNet(GND)
    for seq in gnd_paths:
        pts = [absxy(n) for n in seq]
        for a, c in zip(pts, pts[1:]):
            add_trk(a, c, gnet); n_trk += 1
        log.append(f"  GND  corridoio {len(seq)-1} passi {balls[seq[0]][0]} -> ({pts[-1][0]:.3f},{pts[-1][1]:.3f})")
    return n_uv, n_trk, log

for k, (extra, paths, gnd_paths) in enumerate(ok_combos):
    bd = p.LoadBoard(path)
    n_uv, n_trk, log = build(bd, paths, gnd_paths)
    z1 = [z for z in bd.Zones() if z.GetFirstLayer() == p.In1_Cu and not z.GetIsRuleArea()][0]
    p.ZONE_FILLER(bd).Fill(bd.Zones())
    pieces = z1.GetFilledPolysList(p.In1_Cu).OutlineCount()
    print(f"combinazione {k}: corridoi {len(extra)} nodi, lunghezza uscite {sum(len(v) for v in paths.values())}, piano In1 in {pieces} pezzi (uniti dalle piste GND)")
    if True:
        p.SaveBoard(path, bd)
        print("\n".join(log))
        print(f"creati: {n_uv} microvia, {n_trk} segmenti su In1 (uscite + corridoi GND), {len(paths)} via di fanout")
        break
else:
    sys.exit("nessuna combinazione lascia il piano In1 in un pezzo: niente salvato")
