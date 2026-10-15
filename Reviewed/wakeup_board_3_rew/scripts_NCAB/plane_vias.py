"""Chiude i collegamenti verso i piani: per ogni pad ancora scollegato di una net con piano
cerca il punto libero piu vicino, ci mette un via passante 0.45/0.20 e lo collega al pad con
una pista da 0.10 mm. Il via deve cadere dentro la zona della propria net.
Vincoli: 0.10 dal rame di altre net, 0.15 via-pista, 0.25 via-via, 0.20 rame-foro,
0.45 tra fori, 0.30 dal bordo.
Uso: python.exe plane_vias.py <board.kicad_pcb> <drc.json> [--apply]
"""
import sys, json, math
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
bp, dp = sys.argv[1], sys.argv[2]
APPLY = "--apply" in sys.argv
NETS = ["FLEX_GND", "3V3", "3V3_AON", "REG_IN_MAIN", "BAT_RAW", "BAT_PROT", "BOOST_OUT"]
VIA_D, VIA_H, TW = 0.45, 0.20, 0.10
R_EDGE = 17.0 - 0.30 - VIA_D / 2
MAXR = 3.0

b = p.LoadBoard(bp)
drc = json.load(open(dp, encoding="utf8"))
other_pads, other_segs, other_vias, new_vias = [], [], [], []


def segdist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def rectdist(px, py, r):
    dx = max(r[0] - px, 0, px - r[2])
    dy = max(r[1] - py, 0, py - r[3])
    return math.hypot(dx, dy)


def via_ok(x, y, net):
    if math.hypot(x, y) > R_EDGE:
        return False
    for r in other_pads:
        d = rectdist(x, y, r)
        if d < VIA_D / 2 + 0.10 or d < VIA_H / 2 + 0.20:
            return False
    for vx, vy, vr, nn in other_vias + new_vias:
        d = math.hypot(x - vx, y - vy)
        if nn == net:
            if d < VIA_H + 0.25:            # foro-foro tra via della stessa net
                return False
        elif d < VIA_D / 2 + vr + 0.25:     # via-via tra net diverse
            return False
    for x1, y1, x2, y2, hw, lay, nn in other_segs:
        if segdist(x, y, x1, y1, x2, y2) < VIA_D / 2 + hw + 0.15:
            return False
    return True


def seg_free(x1, y1, x2, y2, layer, net):
    n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 0.05))
    for k in range(n + 1):
        x = x1 + (x2 - x1) * k / n
        y = y1 + (y2 - y1) * k / n
        for r in other_pads:
            if r[4] == layer and rectdist(x, y, r) < TW / 2 + 0.10:
                return False
        for vx, vy, vr, nn in other_vias + new_vias:
            if nn != net and math.hypot(x - vx, y - vy) < vr + TW / 2 + 0.15:
                return False
        for sx1, sy1, sx2, sy2, hw, lay, nn in other_segs:
            if lay == layer and segdist(x, y, sx1, sy1, sx2, sy2) < TW / 2 + hw + 0.10:
                return False
    return True


def paths(px, py, vx, vy):
    """percorsi possibili pad -> via: diretto, a gomito, a 45 gradi"""
    dx, dy = vx - px, vy - py
    out = [[(px, py), (vx, vy)]]
    out.append([(px, py), (px, vy), (vx, vy)])
    out.append([(px, py), (vx, py), (vx, vy)])
    s = min(abs(dx), abs(dy))
    sx = math.copysign(s, dx); sy = math.copysign(s, dy)
    out.append([(px, py), (px + sx, py + sy), (vx, vy)])
    out.append([(px, py), (vx - sx, vy - sy), (vx, vy)])
    return out


def path_ok(pts, layer, net):
    return all(seg_free(a[0], a[1], c[0], c[1], layer, net) for a, c in zip(pts, pts[1:]))


def inside_zone(zs, x, y, margin=0.25):
    for z in zs:
        lay = z.GetFirstLayer()
        if not z.HitTestFilledArea(lay, p.VECTOR2I(mm(x), mm(y)), 0):
            continue
        if all(z.HitTestFilledArea(lay, p.VECTOR2I(mm(x + dx), mm(y + dy)), 0)
               for dx, dy in ((margin, 0), (-margin, 0), (0, margin), (0, -margin))):
            return True
    return False


made, failed = [], []
for NET in NETS:
    zs = [z for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() == NET]
    if not zs:
        continue
    # il vincolo "dentro la zona" serve solo dove il piano e diviso in regioni (In9);
    # sui piani che coprono tutto il disco il via si collega comunque al riempimento
    split = all(z.GetFirstLayer() == p.In9_Cu for z in zs)
    want = set()
    for v in drc.get("unconnected_items", []):
        for i in v["items"]:
            if "Piazzola" in i["description"] and f"[{NET}]" in i["description"]:
                want.add((round(i["pos"]["x"], 3), round(i["pos"]["y"], 3)))
    pads = []
    for f in b.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname() != NET:
                continue
            if (round(tomm(pd.GetPosition().x), 3), round(tomm(pd.GetPosition().y), 3)) in want:
                pads.append((f, pd))
    if not pads:
        continue
    other_pads.clear(); other_segs.clear(); other_vias.clear()
    for f in b.GetFootprints():
        for pd in f.Pads():
            if pd.GetNetname() == NET:
                continue
            bb = pd.GetBoundingBox()
            seq = pd.GetLayerSet().Seq()
            other_pads.append((tomm(bb.GetLeft()), tomm(bb.GetTop()), tomm(bb.GetRight()),
                               tomm(bb.GetBottom()), seq[0] if seq else p.F_Cu, pd.GetNetname()))
    for t in b.GetTracks():
        if t.GetNetname() == NET:
            continue
        if t.GetClass() == "PCB_VIA":
            other_vias.append((tomm(t.GetPosition().x), tomm(t.GetPosition().y),
                               tomm(t.GetWidth(p.F_Cu)) / 2, t.GetNetname()))
        else:
            other_segs.append((tomm(t.GetStart().x), tomm(t.GetStart().y), tomm(t.GetEnd().x),
                               tomm(t.GetEnd().y), tomm(t.GetWidth()) / 2, t.GetLayer(), t.GetNetname()))
    ok = ko = 0
    for f, pd in pads:
        px, py = tomm(pd.GetPosition().x), tomm(pd.GetPosition().y)
        bb = pd.GetBoundingBox()
        half = math.hypot(tomm(bb.GetRight()) - tomm(bb.GetLeft()),
                          tomm(bb.GetBottom()) - tomm(bb.GetTop())) / 2
        seq = pd.GetLayerSet().Seq()
        layer = seq[0] if seq else p.F_Cu
        best, r = None, half + VIA_D / 2 + 0.10
        while r < half + MAXR and best is None:
            for a in range(0, 360, 5):
                x = px + r * math.cos(math.radians(a))
                y = py + r * math.sin(math.radians(a))
                if split and not inside_zone(zs, x, y): continue
                if not via_ok(x, y, NET): continue
                for pts in paths(px, py, x, y):
                    if path_ok(pts, layer, NET):
                        best = (x, y, pts)
                        break
                if best: break
            r += 0.05
        if best:
            new_vias.append((best[0], best[1], VIA_D / 2, NET))
            made.append((NET, best[2], best[0], best[1], layer))
            ok += 1
        else:
            failed.append((NET, f.GetReference(), pd.GetNumber(), px, py))
            ko += 1
    print(f"{NET:12s} pad da collegare {len(pads):3d} -> via piazzati {ok:3d}, senza spazio {ko:3d}")

print(f"TOTALE via piazzati {len(made)}, non riusciti {len(failed)}")
for r in failed[:12]:
    print(f"   {r[0]:12s} {r[1]}.{r[2]} ({r[3]:.2f},{r[4]:.2f})")

if APPLY and made:
    for NET, pts, vx, vy, layer in made:
        net = b.FindNet(NET)
        v = p.PCB_VIA(b); b.Add(v)
        v.SetPosition(p.VECTOR2I(mm(vx), mm(vy)))
        v.SetViaType(p.VIATYPE_THROUGH); v.SetLayerPair(p.F_Cu, p.B_Cu)
        v.SetDrill(mm(VIA_H)); v.SetWidth(mm(VIA_D)); v.SetNet(net)
        for a, c in zip(pts, pts[1:]):
            t = p.PCB_TRACK(b); b.Add(t)
            t.SetStart(p.VECTOR2I(mm(a[0]), mm(a[1]))); t.SetEnd(p.VECTOR2I(mm(c[0]), mm(c[1])))
            t.SetWidth(mm(TW)); t.SetLayer(layer); t.SetNet(net)
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(bp, b)
    print("salvato")
else:
    print("(analisi soltanto)")
