"""Seconda pulizia: elimina via e piste (non bloccati) coinvolti in cortocircuiti,
ponti di maschera, rame-foro e clearance di net class. Le connessioni relative
restano da fare a mano.
Uso: python.exe cleanup2.py <board.kicad_pcb> <drc.json>
"""
import sys, json, re, math
import pcbnew as p
mm, tomm = p.FromMM, p.ToMM
bp, dp = sys.argv[1], sys.argv[2]
b = p.LoadBoard(bp); r = json.load(open(dp, encoding='utf8'))
items = list(b.GetTracks())

def find(desc, pos):
    net = re.search(r'\[([^\]]+)\]', desc)
    if not net: return None
    net = net.group(1)
    isvia = desc.strip().startswith(('Via', 'Microvia'))
    best, bd = None, 1e9
    for t in items:
        if t.GetNetname() != net: continue
        if isvia != (t.GetClass() == 'PCB_VIA'): continue
        if t.GetClass() == 'PCB_VIA':
            d = math.hypot(tomm(t.GetPosition().x) - pos['x'], tomm(t.GetPosition().y) - pos['y'])
        else:
            lay = re.search(r' su (\S+),', desc)
            if lay and b.GetLayerName(t.GetLayer()) != lay.group(1): continue
            d = min(math.hypot(tomm(t.GetStart().x) - pos['x'], tomm(t.GetStart().y) - pos['y']),
                    math.hypot(tomm(t.GetEnd().x) - pos['x'], tomm(t.GetEnd().y) - pos['y']))
        if d < bd: best, bd = t, d
    return best if bd < 0.02 else None

TYPES = {'shorting_items', 'solder_mask_bridge', 'hole_clearance'}
dele, miss = {}, 0
for v in r['violations']:
    t = v['type']
    if t not in TYPES and not (t == 'clearance' and 'netclass' in v['description']): continue
    for i in v['items']:
        d = i['description']
        if 'Piazzola' in d: continue          # i pad non si toccano
        it = find(d, i['pos'])
        if it is None: miss += 1
        elif not it.IsLocked(): dele[id(it)] = (it, t)
import collections
print('da eliminare:', collections.Counter(t for _, t in dele.values()), ' non identificati:', miss)
for it, _ in dele.values(): b.Remove(it)
p.ZONE_FILLER(b).Fill(b.Zones()); p.SaveBoard(bp, b); print('salvato')
