"""Elimina i monconi (piste con un capo scollegato) lasciati dalle pulizie, in modo
iterativo e senza toccare gli elementi bloccati.
Uso: python.exe clean_dangling.py <board.kicad_pcb> <drc.json>"""
import sys, json, re, math
import pcbnew as p
mm, tomm = p.FromMM, p.ToMM
bp, dp = sys.argv[1], sys.argv[2]
b = p.LoadBoard(bp); r = json.load(open(dp, encoding='utf8'))
dele = {}
for v in r['violations']:
    if v['type'] not in ('track_dangling', 'via_dangling'): continue
    for i in v['items']:
        d = i['description']; pos = i['pos']
        net = re.search(r'\[([^\]]+)\]', d)
        if not net: continue
        isvia = d.strip().startswith(('Via', 'Microvia'))
        best, bd = None, 1e9
        for t in b.GetTracks():
            if t.GetNetname() != net.group(1) or (t.GetClass() == 'PCB_VIA') != isvia: continue
            if isvia:
                dd = math.hypot(tomm(t.GetPosition().x) - pos['x'], tomm(t.GetPosition().y) - pos['y'])
            else:
                dd = min(math.hypot(tomm(t.GetStart().x) - pos['x'], tomm(t.GetStart().y) - pos['y']),
                         math.hypot(tomm(t.GetEnd().x) - pos['x'], tomm(t.GetEnd().y) - pos['y']))
            if dd < bd: best, bd = t, dd
        if best is not None and bd < 0.02 and not best.IsLocked(): dele[id(best)] = best
print('monconi eliminati:', len(dele))
for t in dele.values(): b.Remove(t)
p.ZONE_FILLER(b).Fill(b.Zones()); p.SaveBoard(bp, b); print('salvato')
