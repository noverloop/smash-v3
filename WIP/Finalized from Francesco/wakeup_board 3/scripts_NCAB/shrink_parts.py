"""Riduce la taglia di alcuni passivi per liberare corridoi di routing.
- 0805 -> 0603: C_MAG2, C_AON_IN, C_AON_OUT, C_TMR_LDO (1 uF X7R)
- 0603 -> 0402: C_MAG_C1 (220 nF), C_WBA_PI1, C_WBA_PI2 (0.5 pF RF)
- test point: pad da 1.5 a 1.0 mm
Mantiene posizione, rotazione, lato, riferimento e net di ogni piazzola.
Uso: python.exe shrink_parts.py <board.kicad_pcb> [--apply]
"""
import sys, os
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
bp = os.path.abspath(sys.argv[1])
APPLY = "--apply" in sys.argv
LIB = os.path.join(os.path.dirname(bp), "footprints", "SmashWakeupBoard.pretty")
b = p.LoadBoard(bp)

SWAP = {
    "C_MAG2": "Capacitor_SMD_C_0603_1608Metric",
    "C_AON_IN": "Capacitor_SMD_C_0603_1608Metric",
    "C_AON_OUT": "Capacitor_SMD_C_0603_1608Metric",
    "C_TMR_LDO": "Capacitor_SMD_C_0603_1608Metric",
    "C_MAG_C1": "Capacitor_SMD_C_0402_1005Metric",
    "C_WBA_PI1": "Capacitor_SMD_C_0402_1005Metric",
    "C_WBA_PI2": "Capacitor_SMD_C_0402_1005Metric",
}
TP_NEW = 1.0

done, tp = [], []
# passo 1: leggo i dati dei componenti da sostituire (dentro il ciclo, per non perdere il tipo)
info = {}
for f in b.GetFootprints():
    ref = f.GetReference()
    if ref in SWAP:
        info[ref] = dict(nets={pd.GetNumber(): pd.GetNetCode() for pd in f.Pads()},
                         pos=p.VECTOR2I(f.GetPosition()), rot=f.GetOrientation(),
                         flip=f.IsFlipped(), val=f.GetValue(),
                         oldfp=str(f.GetFPID().GetLibItemName()))
    if "TestPoint_Pad_D1.5mm" in str(f.GetFPID().GetLibItemName()):
        for pd in f.Pads():
            if abs(tomm(pd.GetSize(p.F_Cu).x) - 1.5) < 0.01:
                tp.append(ref)
                if APPLY:
                    pd.SetSize(p.F_Cu, p.VECTOR2I(mm(TP_NEW), mm(TP_NEW)))

# passo 2: sostituzione
for ref, newfp in SWAP.items():
    d = info.get(ref)
    if d is None:
        print(f"  {ref}: non trovato"); continue
    size_old = "0805" if "0805" in d["oldfp"] else "0603"
    size_new = "0603" if "0603" in newfp else "0402"
    newval = d["val"].replace(size_old, size_new)
    if not APPLY:
        done.append((ref, d["oldfp"], newfp, newval)); continue
    for f in list(b.GetFootprints()):
        if f.GetReference() == ref:
            b.Remove(f); break
    new = p.FootprintLoad(LIB, newfp)
    if new is None:
        print(f"  {ref}: impronta {newfp} non caricabile"); continue
    b.Add(new)
    new.SetFPID(p.LIB_ID("SmashWakeupBoard", newfp))
    new.SetReference(ref); new.SetValue(newval)
    new.SetPosition(d["pos"])
    if d["flip"]:
        new.Flip(d["pos"], False)
    new.SetOrientation(d["rot"])
    for pd in new.Pads():
        if pd.GetNumber() in d["nets"]:
            pd.SetNetCode(d["nets"][pd.GetNumber()])
    done.append((ref, d["oldfp"], newfp, newval))

print("sostituzioni:")
for ref, o, n, v in done:
    print(f"  {ref:14s} {o:34s} -> {n:34s}  valore: {v[:40]}")
print(f"test point ridotti a {TP_NEW} mm: {len(tp)}  {sorted(set(tp))}")

if APPLY:
    b.BuildListOfNets()
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(bp, b)
    print("salvato")
else:
    print("(analisi soltanto)")
