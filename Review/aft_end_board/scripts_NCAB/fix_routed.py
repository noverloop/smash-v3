"""Correzioni post-Freerouting per le regole NCAB (API pcbnew, KiCad 10)."""
import sys, pcbnew as p
mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
b = p.LoadBoard(path)
log = []
SPUR = [{(6.51, -6.55), (6.01, -7.05)}, {(6.01, -7.05), (6.01, -7.15)}, {(6.01, -7.15), (5.7, -7.46)}]
dead = []
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        # via meccanici: pad 0.45 con foro > 0.20 -> anello < 0.125
        if t.GetViaType() == p.VIATYPE_THROUGH and abs(tomm(t.GetWidth(p.F_Cu)) - 0.45) < 1e-3 and tomm(t.GetDrill()) > 0.2001:
            log.append(f"via {t.GetNetname()} @({tomm(t.GetPosition().x):.3f},{tomm(t.GetPosition().y):.3f}) foro {tomm(t.GetDrill())} -> 0.20")
            t.SetDrill(mm(0.20))
    elif t.GetClass() == 'PCB_TRACK':
        if tomm(t.GetWidth()) < 0.0999:
            log.append(f"pista {t.GetNetname()} {b.GetLayerName(t.GetLayer())} {tomm(t.GetWidth())} -> 0.10")
            t.SetWidth(mm(0.10))
        # ramo morto di GPIO_EXT_3 su F.Cu lasciato da Freerouting (3 segmenti)
        if t.GetNetname() == 'GPIO_EXT_3' and t.GetLayer() == p.F_Cu:
            ends = {(round(tomm(t.GetStart().x), 2), round(tomm(t.GetStart().y), 2)),
                    (round(tomm(t.GetEnd().x), 2), round(tomm(t.GetEnd().y), 2))}
            if ends in SPUR:
                dead.append(t)
for t in dead:
    log.append(f"rimossa pista pendente {t.GetNetname()} len {tomm(t.GetLength()):.3f}")
    b.Remove(t)
p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)
print("\n".join(log))
