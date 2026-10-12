"""Reimporta in KiCad il .ses di Freerouting prodotto dal DSN NCAB.
- aggiunge al .ses i padstack dei via esistenti che Freerouting non riscrive in library_out
- riferimenti temporanei MH_POTn ai fori di potting senza riferimento (come all'export)
- ImportSpecctraSES (sostituisce tutte le piste e i via)
- ricrea identici gli elementi bloccati che il .ses non contiene (fanout U_WBA: piste
  su In1 e microvia), presi dalla scheda prima dell'import
- eventuali via gonfiati 0.60 -> 0.45; riferimenti ripristinati; zone riempite
Uso: python.exe import_ses_ncab.py <board.kicad_pcb> <file.ses> <file.dsn>
"""
import sys, os, re
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
board_path, ses_path, dsn_path = (os.path.abspath(a) for a in sys.argv[1:4])

# ---- 1. padstack mancanti nel .ses
ses = open(ses_path, encoding="utf8").read()
dsn = open(dsn_path, encoding="utf8").read()
used = set(re.findall(r'\(via ("[^"]+"|\S+)', ses[ses.find("(network_out"):]))
have = set(re.findall(r'\(padstack ("[^"]+"|\S+)', ses[ses.find("(library_out"):ses.find("(network_out")]))
res_dsn = float(re.search(r'\(resolution um (\d+)\)', dsn).group(1))
res_ses = float(re.search(r'\(resolution um (\d+)\)', ses).group(1))
added = []
for name in sorted(used - have):
    m = re.search(r'\n(\s*)\(padstack ' + re.escape(name) + r'(.*?)\n\1\)', dsn, re.S)
    if not m:
        sys.exit(f"padstack {name} non trovato nel DSN")
    body = m.group(2)
    # DSN in um (senza risoluzione), SES in unita di 1/res um
    body = re.sub(r'\(circle (\S+) ([\d.]+)\)',
                  lambda k: f"(circle {k.group(1)} {int(round(float(k.group(2)) * res_ses))} 0 0)", body)
    block = f"\n      (padstack {name}{body}\n      )"
    i = ses.find("(library_out") + len("(library_out")
    ses = ses[:i] + block + ses[i:]
    added.append(name)
ses_fixed = ses_path.replace(".ses", "_fix.ses")
open(ses_fixed, "w", encoding="utf8").write(ses)
print("padstack aggiunti al .ses:", added)

# ---- 2. scheda e istantanea degli elementi bloccati
b = p.LoadBoard(board_path)

def key(t):
    if t.GetClass() == "PCB_VIA":
        return ("V", t.GetNetname(), t.GetPosition().x, t.GetPosition().y, t.TopLayer(), t.BottomLayer())
    return ("T", t.GetNetname(), t.GetLayer(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y)

locked = {}
for t in b.GetTracks():
    if t.IsLocked():
        if t.GetClass() == "PCB_VIA":
            locked[key(t)] = dict(kind="V", net=t.GetNetname(), pos=t.GetPosition(), vt=t.GetViaType(),
                                  top=t.TopLayer(), bot=t.BottomLayer(), drill=t.GetDrill(), w=t.GetWidth(p.F_Cu))
        else:
            locked[key(t)] = dict(kind="T", net=t.GetNetname(), layer=t.GetLayer(), s=t.GetStart(),
                                  e=t.GetEnd(), w=t.GetWidth())
n_before = len([t for t in b.GetTracks()])

tmp = []
for f in b.GetFootprints():
    if not f.GetReference().strip():
        tmp.append(f)
        f.SetReference(f"MH_POT{len(tmp)}")

# KiCad 10 ruota di 180 i componenti back a +-90 durante l'import: posizioni salvate e ripristinate
place = {f.m_Uuid.AsString(): (p.VECTOR2I(f.GetPosition()), f.GetOrientation(), f.IsFlipped()) for f in b.GetFootprints()}
if not p.ImportSpecctraSES(b, ses_fixed):
    sys.exit("ImportSpecctraSES fallito: niente salvato")

moved = 0
for f in b.GetFootprints():
    pos, rot, flip = place[f.m_Uuid.AsString()]
    if f.IsFlipped() != flip:
        f.Flip(f.GetPosition(), False)
    if f.GetOrientation() != rot or f.GetPosition() != pos:
        f.SetOrientation(rot); f.SetPosition(pos); moved += 1
print("componenti riportati alla posizione originale dopo l'import:", moved)

# ---- 3. ripristino degli elementi bloccati mancanti
present = {}
for t in b.GetTracks():
    present[key(t)] = t
restored = 0
for k, d in locked.items():
    t = present.get(k)
    if t is not None:
        t.SetLocked(True)
        if d["kind"] == "V":
            t.SetViaType(d["vt"]); t.SetDrill(d["drill"]); t.SetWidth(d["w"])
        continue
    net = b.FindNet(d["net"])
    if d["kind"] == "V":
        v = p.PCB_VIA(b); b.Add(v)
        v.SetPosition(d["pos"]); v.SetViaType(d["vt"]); v.SetLayerPair(d["top"], d["bot"])
        v.SetDrill(d["drill"]); v.SetWidth(d["w"]); v.SetNet(net); v.SetLocked(True)
    else:
        t = p.PCB_TRACK(b); b.Add(t)
        t.SetStart(d["s"]); t.SetEnd(d["e"]); t.SetWidth(d["w"]); t.SetLayer(d["layer"])
        t.SetNet(net); t.SetLocked(True)
    restored += 1

# ---- 4. via gonfiati -> 0.45 (se presenti)
shrunk = 0
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA" and t.GetViaType() == p.VIATYPE_THROUGH and abs(tomm(t.GetWidth(p.F_Cu)) - 0.60) < 1e-3:
        t.SetWidth(mm(0.45)); shrunk += 1

for f in tmp:
    f.SetReference("")

vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
print(f"elementi prima: {n_before}, dopo: {len(list(b.GetTracks()))}")
print(f"bloccati: {len(locked)}, ripristinati: {restored}, via 0.60->0.45: {shrunk}")
print("via per tipo/misura:", sorted({(str(v.GetViaType()), round(tomm(v.GetWidth(p.F_Cu)), 3), round(tomm(v.GetDrill()), 3)) for v in vias}))
p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(board_path, b)
print("salvato")
