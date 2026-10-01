"""Pulizia del routing prodotto da Freerouting:
 - elimina le piste che cortocircuitano pad di altre net (segnalate dal DRC)
 - porta a 0.10 mm le piste sotto il minimo NCAB (se poi creano conflitti, le elimina)
 - riempie le zone e salva
Uso: python.exe cleanup_routing.py <board.kicad_pcb> <drc.json>
"""
import sys, json, re, math
import pcbnew as p
mm, tomm = p.FromMM, p.ToMM
board_path, drc_path = sys.argv[1], sys.argv[2]
b = p.LoadBoard(board_path)
r = json.load(open(drc_path, encoding='utf8'))

tracks = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK']
def match(desc, pos):
    """trova la pista descritta dal DRC: net, layer, lunghezza, posizione"""
    mnet = re.search(r'\[([^\]]+)\]', desc); mlay = re.search(r' su (\S+),', desc)
    mlen = re.search(r'lung\. ([\d.]+) mm', desc)
    if not (mnet and mlay and mlen): return None
    net, lay, ln = mnet.group(1), mlay.group(1), float(mlen.group(1))
    best, bd = None, 1e9
    for t in tracks:
        if t.GetNetname() != net or b.GetLayerName(t.GetLayer()) != lay: continue
        if abs(tomm(t.GetLength()) - ln) > 0.002: continue
        d = min(math.hypot(tomm(t.GetStart().x) - pos['x'], tomm(t.GetStart().y) - pos['y']),
                math.hypot(tomm(t.GetEnd().x) - pos['x'], tomm(t.GetEnd().y) - pos['y']))
        if d < bd: best, bd = t, d
    return best if bd < 0.01 else None

to_del, nomatch = {}, 0
for v in r['violations']:
    if v['type'] != 'shorting_items': continue
    for i in v['items']:
        if 'Pista' not in i['description']: continue
        t = match(i['description'], i['pos'])
        if t is None: nomatch += 1
        elif not t.IsLocked(): to_del[id(t)] = t
print(f"cortocircuiti: piste da eliminare {len(to_del)} (non identificate: {nomatch})")
for t in to_del.values(): b.Remove(t)

widened = []
for t in [x for x in b.GetTracks() if x.GetClass() == 'PCB_TRACK']:
    if not t.IsLocked() and tomm(t.GetWidth()) < 0.0999:
        widened.append((t, t.GetWidth()))
        t.SetWidth(mm(0.10))
print(f"piste allargate a 0.10 mm: {len(widened)}")

p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(board_path, b)
print("salvato")
