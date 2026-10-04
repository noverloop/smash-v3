"""Fanout di U_G0B1_FIN (STM32G0B1, UFBGA64 passo 0.5 mm, pad 0.224) su F.Cu. API pcbnew KiCad 10.

- area regola "BGA_G0B1_FIN" (attiva le regole NCAB BGA del .kicad_dru: pista e isolamento 0.08)
- segnali e 3V3: percorso minimo su F.Cu (griglia 0.025, pista 0.08, isolamento 0.08) fino a una
  via passante 0.45/0.20 fuori dal corpo del chip, oppure fino a rame della stessa net gia collegato
  a una via (le sfere 3V3 vicine si uniscono, ma ogni gruppo scende al piano)
- FLEX_GND: microvia laser 0.25/0.10 F.Cu -> In1.Cu (piano di massa) nel punto libero piu vicino
- distanze delle via passanti: 0.10 dai pad, 0.15 dalle piste (FAB), 0.25 tra via, 0.25 tra fori
- altri segnali: solo uscita dal campo sfere fino a un punto di fuga fuori dal corpo (+0.35 mm), distanziato
  perche una pista da 0.10 possa proseguire; il resto lo sbroglia Freerouting (niente via inutili vicino al chip)
- prova piu ordini di instradamento e tiene il migliore; tutto bloccato (locked) per Freerouting
Uso: python.exe fanout_g0b1.py <board.kicad_pcb> [--apply] [--tries N]
"""
import sys, math, collections, random
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
APPLY = "--apply" in sys.argv
TRIES = int(sys.argv[sys.argv.index("--tries") + 1]) if "--tries" in sys.argv else 12
b = p.LoadBoard(path)
U = [f for f in b.GetFootprints() if f.GetReference() == "U_G0B1_FIN"][0]
CX, CY = tomm(U.GetPosition().x), tomm(U.GetPosition().y)
if any(z.GetIsRuleArea() and z.GetZoneName().startswith("BGA") for z in b.Zones()):
    sys.exit("fanout gia presente (area BGA trovata): niente fatto")

TW, CL = 0.08, 0.08                 # dentro l'area BGA
VD, VH = 0.45, 0.20                 # via passante
UD, UH = 0.25, 0.10                 # microvia
GND = "FLEX_GND"
G = 0.025
BODY = 2.5                          # meta lato del corpo 5x5
AREA = BODY + 2.0                   # area regola: corpo + 2.0 mm
X0, X1, Y0, Y1 = CX - AREA, CX + AREA, CY - AREA, CY + AREA
nx, ny = int(round((X1 - X0) / G)) + 1, int(round((Y1 - Y0) / G)) + 1
R_EDGE = 17.0 - 0.30


def seg_d(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


# ---------------------------------------------------------------- ostacoli statici
padsF, padsAll = [], []         # (x, y, hx, hy, rotondo, net)
for f in b.GetFootprints():
    for q in f.Pads():
        x, y = tomm(q.GetPosition().x), tomm(q.GetPosition().y)
        if abs(x - CX) > AREA + 2 or abs(y - CY) > AREA + 2:
            continue
        bb = q.GetBoundingBox()
        rec = (x, y, (tomm(bb.GetRight()) - tomm(bb.GetLeft())) / 2,
               (tomm(bb.GetBottom()) - tomm(bb.GetTop())) / 2, q.GetShape() == p.PAD_SHAPE_CIRCLE, q.GetNetname())
        hole = q.GetDrillSize().x > 0
        if q.IsOnLayer(p.F_Cu) or hole:
            padsF.append(rec)
        if q.IsOnLayer(p.F_Cu) or q.IsOnLayer(p.B_Cu) or hole:
            padsAll.append(rec)


def pad_d(px, py, r):
    x, y, hx, hy, rnd = r[:5]
    if rnd:
        return math.hypot(px - x, py - y) - hx
    return math.hypot(max(abs(px - x) - hx, 0), max(abs(py - y) - hy, 0))


def cells_near(x0, y0, x1, y1):
    i0 = max(0, int((x0 - X0) / G)); i1 = min(nx - 1, int((x1 - X0) / G) + 1)
    j0 = max(0, int((y0 - Y0) / G)); j1 = min(ny - 1, int((y1 - Y0) / G) + 1)
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            yield i * ny + j, X0 + i * G, Y0 + j * G


# mezzeria pista: distanza dai pad F.Cu di altre net (per net) -> mappa pad per net
PADBLK = {}                      # net -> bytearray bloccata dai pad di altre net
PAD_OWN = {}                     # net -> {id pad: celle dentro il pad}
lim = TW / 2 + CL
base = bytearray(nx * ny)        # bloccata da qualunque pad (senza net o di qualunque net)
padcells = []                    # (net, [celle con d<lim], [celle dentro il pad])
for r in padsF:
    x, y, hx, hy = r[:4]
    near, inside = [], []
    for k, px, py in cells_near(x - hx - lim, y - hy - lim, x + hx + lim, y + hy + lim):
        d = pad_d(px, py, r)
        if d < lim:
            near.append(k)
        if d <= 0:
            inside.append(k)
    padcells.append((r[5], near, inside, (x, y)))


def padblk(net):
    if net not in PADBLK:
        blk = bytearray(nx * ny)
        for n, near, inside, _ in padcells:
            if n == net and n:
                continue
            for k in near:
                blk[k] = 1
        PADBLK[net] = blk
    return PADBLK[net]


# posizioni ammesse per le via passanti e le microvie (solo ostacoli statici)
VIA_S = bytearray(nx * ny)
UV_S = bytearray(nx * ny)
for k in range(nx * ny):
    i, j = divmod(k, ny)
    x, y = X0 + i * G, Y0 + j * G
    if math.hypot(x, y) > R_EDGE - VD / 2:
        continue
    dmin = min((pad_d(x, y, r) for r in padsAll), default=9)
    under = abs(x - CX) < BODY + VD / 2 + 0.05 and abs(y - CY) < BODY + VD / 2 + 0.05
    inarea = abs(x - CX) <= AREA - VD / 2 and abs(y - CY) <= AREA - VD / 2
    if not under and inarea and dmin >= VD / 2 + 0.15:
        VIA_S[k] = 1
    dF = min((pad_d(x, y, r) for r in padsF), default=9)
    if dF >= max(UD / 2 + CL, UH / 2 + 0.20):     # NCAB rame-foro 0.20 vale anche microvia <-> pad
        UV_S[k] = 1

ESC_OUT = BODY + 0.35              # punto di fuga dei segnali: fuori dal corpo di almeno 0.35 mm
ESC_S = bytearray(nx * ny)
for k in range(nx * ny):
    i, j = divmod(k, ny)
    x, y = X0 + i * G, Y0 + j * G
    if max(abs(x - CX), abs(y - CY)) < ESC_OUT or max(abs(x - CX), abs(y - CY)) > AREA - 0.3:
        continue
    if math.hypot(x, y) > R_EDGE - 0.2:
        continue
    if min((pad_d(x, y, r) for r in padsF), default=9) >= 0.05 + 0.10 + 0.05:
        ESC_S[k] = 1
VIA_NETS = {"3V3"}                 # net che scendono subito a un piano con una via passante

balls = {q.GetNumber(): q for q in U.Pads()}
ROWS = "ABCDEFGH"


def ring(k):
    r, c = ROWS.index(k[0]), int(k[1:]) - 1
    return min(r, c, 7 - r, 7 - c)


def ball_xy(k):
    q = balls[k]
    return tomm(q.GetPosition().x), tomm(q.GetPosition().y)


def run(order):
    placed, vias, uvias, res, fail = [], [], [], [], []
    for kb in order:
        net = balls[kb].GetNetname()
        sx, sy = ball_xy(kb)
        blk = bytearray(padblk(net))
        goal = bytearray(nx * ny)
        for ax, ay, bx, by, n in placed:
            own = n == net
            L = TW / 2 if own else TW + CL
            for k, px, py in cells_near(min(ax, bx) - L, min(ay, by) - L, max(ax, bx) + L, max(ay, by) + L):
                d = seg_d(px, py, ax, ay, bx, by)
                if own:
                    if d <= TW / 2:
                        goal[k] = 1
                elif d < L:
                    blk[k] = 1
        for vx, vy, n, rad in vias + uvias:
            own = n == net
            L = rad if own else rad + TW / 2 + (0.15 if rad > 0.2 else CL)
            for k, px, py in cells_near(vx - L, vy - L, vx + L, vy + L):
                d = math.hypot(px - vx, py - vy)
                if own:
                    if d <= rad:
                        goal[k] = 1
                elif d < L:
                    blk[k] = 1
        si, sj = int(round((sx - X0) / G)), int(round((sy - Y0) / G))
        for k, px, py in cells_near(sx - 0.12, sy - 0.12, sx + 0.12, sy + 0.12):
            if math.hypot(px - sx, py - sy) <= 0.112:
                blk[k] = 0
                goal[k] = 0
        start = si * ny + sj
        prev = {start: -1}
        dq = collections.deque([start])
        end = kind = None
        while dq:
            k = dq.popleft()
            i, j = divmod(k, ny)
            x, y = X0 + i * G, Y0 + j * G
            if k != start and goal[k]:
                end, kind = k, "rame"
                break
            if net == GND:
                ok = UV_S[k] and math.hypot(x - sx, y - sy) >= 0.112 + UD / 2 + CL
                if ok:
                    for ax, ay, bx, by, n in placed:
                        if n != net and seg_d(x, y, ax, ay, bx, by) < UD / 2 + TW / 2 + CL:
                            ok = False; break
                if ok:
                    for vx, vy, n, rad in vias + uvias:
                        dd = math.hypot(x - vx, y - vy)
                        if (n != net and dd < UD / 2 + rad + CL) or (n == net and dd < UH / 2 + rad + 0.15):
                            ok = False; break
                if ok:
                    end, kind = k, "microvia"
                    break
            elif net not in VIA_NETS:
                if ESC_S[k]:
                    ok = True
                    for ax, ay, bx, by, n in placed:
                        if n != net and seg_d(x, y, ax, ay, bx, by) < 0.05 + 0.10 + TW / 2 + 0.03:
                            ok = False; break
                    if ok:
                        for vx, vy, n, rad in vias + uvias:
                            if n != net and math.hypot(x - vx, y - vy) < rad + 0.15 + 0.05:
                                ok = False; break
                    if ok:
                        end, kind = k, "fuga"
                        break
            elif VIA_S[k]:
                ok = True
                for ax, ay, bx, by, n in placed:
                    if n != net and seg_d(x, y, ax, ay, bx, by) < VD / 2 + TW / 2 + 0.15:
                        ok = False; break
                if ok:
                    for vx, vy, n, rad in vias + uvias:
                        dd = math.hypot(x - vx, y - vy)
                        if (n != net and dd < VD / 2 + rad + 0.25) or (n == net and dd < VH / 2 + rad + 0.25):
                            ok = False; break
                if ok:
                    end, kind = k, "via"
                    break
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                a, c = i + di, j + dj
                if not (0 <= a < nx and 0 <= c < ny):
                    continue
                kk = a * ny + c
                if kk in prev or blk[kk]:
                    continue
                if di and dj and (blk[a * ny + j] or blk[i * ny + c]):
                    continue
                prev[kk] = k
                dq.append(kk)
        if end is None:
            fail.append(kb)
            continue
        pts = []
        k = end
        while k != -1:
            i, j = divmod(k, ny)
            pts.append((X0 + i * G, Y0 + j * G))
            k = prev[k]
        pts.reverse()
        pts[0] = (sx, sy)
        s = [pts[0]]
        for m in range(1, len(pts) - 1):
            a, c, d = s[-1], pts[m], pts[m + 1]
            if abs((c[0] - a[0]) * (d[1] - a[1]) - (c[1] - a[1]) * (d[0] - a[0])) > 1e-9:
                s.append(c)
        s.append(pts[-1])
        for a, c in zip(s, s[1:]):
            placed.append((a[0], a[1], c[0], c[1], net))
        if kind == "via":
            vias.append((s[-1][0], s[-1][1], net, VD / 2))
        elif kind == "microvia":
            uvias.append((s[-1][0], s[-1][1], net, UD / 2))
        res.append((kb, net, kind, s))
    L = sum(math.hypot(c[0] - a[0], c[1] - a[1]) for _, _, _, s in res for a, c in zip(s, s[1:]))
    return res, fail, vias, uvias, L


todo = [k for k, q in balls.items() if q.GetNetname()]
orders = [sorted(todo, key=lambda k: (-ring(k), k)), sorted(todo, key=lambda k: (ring(k), k))]
rnd = random.Random(7)
for _ in range(max(0, TRIES - 2)):
    o = todo[:]
    rnd.shuffle(o)
    o.sort(key=lambda k: ring(k) + rnd.random() * 2.5, reverse=True)
    orders.append(o)
best = None
for n, o in enumerate(orders):
    r = run(o)
    print("  ordine %2d: riuscite %2d/%d, lunghezza %.1f mm, via %d, microvia %d" % (
        n, len(r[0]), len(todo), r[4], len(r[2]), len(r[3])))
    if best is None or (len(r[1]), r[4]) < (len(best[1]), best[4]):
        best = r
    if not r[1] and n >= 2:
        break
# strappa e ripeti: le sfere fallite passano in testa all'ordine, le altre si adattano
last = best
for it in range(10):
    if not best[1] or not last[1]:
        break
    order = last[1] + [kb for kb, _, _, _ in last[0]]
    last = run(order)
    print("  ripetizione %2d: riuscite %2d/%d, fallite %s" % (it + 1, len(last[0]), len(todo), last[1] or "-"))
    if (len(last[1]), last[4]) < (len(best[1]), best[4]):
        best = last
res, fail, vias, uvias, L = best
print("\nmigliore: riuscite %d/%d, fallite %s, via %d, microvia %d, piste %.1f mm" % (
    len(res), len(todo), fail or "-", len(vias), len(uvias), L))
for kb, net, kind, s in sorted(res):
    print("  %-4s %-16s anello %d -> %-8s %s" % (kb, net, ring(kb) + 1, kind,
          "" if kind == "rame" else "(%.2f,%.2f)" % s[-1]))

if APPLY and not fail:
    area = p.ZONE(b)
    area.SetIsRuleArea(True)
    area.SetZoneName("BGA_G0B1_FIN")
    area.SetLayerSet(p.LSET.AllCuMask())
    for fn in ("SetDoNotAllowTracks", "SetDoNotAllowVias", "SetDoNotAllowPads",
               "SetDoNotAllowZoneFills", "SetDoNotAllowFootprints"):
        getattr(area, fn)(False)
    ol = area.Outline()
    ol.NewOutline()
    for x, y in ((X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)):
        ol.Append(mm(x), mm(y))
    b.Add(area)
    for kb, net, kind, s in res:
        n = b.FindNet(net)
        for a, c in zip(s, s[1:]):
            t = p.PCB_TRACK(b)
            b.Add(t)
            t.SetStart(p.VECTOR2I(mm(a[0]), mm(a[1])))
            t.SetEnd(p.VECTOR2I(mm(c[0]), mm(c[1])))
            t.SetWidth(mm(TW)); t.SetLayer(p.F_Cu); t.SetNet(n); t.SetLocked(True)
    for x, y, net, rad in vias + uvias:
        v = p.PCB_VIA(b)
        b.Add(v)
        v.SetPosition(p.VECTOR2I(mm(x), mm(y)))
        if rad > 0.2:
            v.SetViaType(p.VIATYPE_THROUGH); v.SetLayerPair(p.F_Cu, p.B_Cu)
            v.SetWidth(mm(VD)); v.SetDrill(mm(VH))
        else:
            v.SetViaType(p.VIATYPE_MICROVIA); v.SetLayerPair(p.F_Cu, p.In1_Cu)
            v.SetWidth(mm(UD)); v.SetDrill(mm(UH))
        v.SetNet(b.FindNet(net)); v.SetLocked(True)
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(path, b)
    print("salvato")
elif APPLY:
    print("NON salvato: ci sono sfere senza percorso")
