"""wakeup_board - review Sjoert: modelli 3D non posizionati correttamente.

Package standard: i modelli del costruttore erano affondati nella scheda o spostati; le impronte
hanno la stessa piedinatura delle impronte KiCad (pin 1 in alto a sinistra), quindi si usano i
modelli standard KiCad (origine al centro, z=0 sul piano, pin 1 coerente), copiati in 3dmodels/.
RR123-1H02-612: modello del costruttore capovolto (sotto la scheda): rotazione X +90, poi
centrato sui pad e appoggiato a z=0.
Le modifiche vanno sia sulle impronte della scheda sia su quelle della libreria del progetto.
Uso: python.exe fix_3d.py <board.kicad_pcb>
"""
import sys, os, re, math, shutil
import pcbnew as p

tomm = p.ToMM
path = sys.argv[1]
prj = os.path.dirname(os.path.abspath(path))
lib = os.path.join(prj, "footprints", "SmashWakeupBoard.pretty")
KI3D = r"C:/Program Files/KiCad/10.0/share/kicad/3dmodels"

STD = {   # impronta -> modello standard KiCad (cartella, file)
    "SOT95P237X125-3N": ("Package_TO_SOT_SMD.3dshapes", "SOT-23.step"),
    "SOT95P237X112-3N": ("Package_TO_SOT_SMD.3dshapes", "SOT-23.step"),
    "SOT96P237X111-3N": ("Package_TO_SOT_SMD.3dshapes", "SOT-23.step"),
    "SOT95P280X145-5N": ("Package_TO_SOT_SMD.3dshapes", "SOT-23-5.step"),
    "SON95P300X300X100-7N-D": ("Package_DFN_QFN.3dshapes", "DFN-6-1EP_3x3mm_P0.95mm_EP1.7x2.6mm.step"),
}
RECENTER = {"RR123-1H02-612": (90.0, 0.0, 0.0)}   # impronta -> rotazione nuova, offset calcolato


def step_corners(fn):
    txt = open(fn, encoding="latin1", errors="ignore").read()
    P = [tuple(map(float, m.groups())) for m in re.finditer(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-\d.Ee+]+)\s*,\s*([-\d.Ee+]+)\s*,\s*([-\d.Ee+]+)\s*\)", txt)]
    xs, ys, zs = zip(*P)
    return [(x, y, z) for x in (min(xs), max(xs)) for y in (min(ys), max(ys)) for z in (min(zs), max(zs))]


def rot(v, rx, ry, rz):
    x, y, z = v
    a = math.radians(rx); y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
    a = math.radians(ry); x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
    a = math.radians(rz); x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    return x, y, z


def recenter_offset(f, fn, r):
    """offset (mm) che centra il modello sui pad (coordinate impronta, Y KiCad in giu) con z min = 0"""
    xs, ys = [], []
    for q in f.Pads():
        c, s = q.GetFPRelativePosition(), q.GetSize(q.GetPrincipalLayer())
        xs += [tomm(c.x) - tomm(s.x) / 2, tomm(c.x) + tomm(s.x) / 2]
        ys += [tomm(c.y) - tomm(s.y) / 2, tomm(c.y) + tomm(s.y) / 2]
    pcx, pcy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    T = [rot(c, *r) for c in step_corners(fn)]
    mx = (min(t[0] for t in T) + max(t[0] for t in T)) / 2
    my = -(min(t[1] for t in T) + max(t[1] for t in T)) / 2      # Y del modello verso l'alto
    zmin = min(t[2] for t in T)
    return pcx - mx, -(pcy - my), -zmin


def fix(f):
    name = f.GetFPID().GetLibItemName().wx_str()
    ms = f.Models()
    if name in STD:
        sub, fn = STD[name]
        dst = os.path.join(prj, "3dmodels", sub)
        os.makedirs(dst, exist_ok=True)
        if not os.path.exists(os.path.join(dst, fn)):
            shutil.copy(os.path.join(KI3D, sub, fn), dst)
        m = p.FP_3DMODEL()
        m.m_Filename = f"${{KIPRJMOD}}/3dmodels/{sub}/{fn}"
        ms.clear()
        ms.push_back(m)
        return f"modello KiCad {fn}"
    if name in RECENTER and len(ms):
        m = ms[0]
        fn = m.m_Filename.replace("${KIPRJMOD}", prj)
        r = RECENTER[name]
        ox, oy, oz = recenter_offset(f, fn, r)
        m.m_Rotation = p.VECTOR3D(*r)
        m.m_Offset = p.VECTOR3D(ox, oy, oz)
        return f"rot {r} offset ({ox:.3f},{oy:.3f},{oz:.3f})"
    return None


# libreria del progetto (impronte non ruotate/specchiate: servono anche per calcolare gli offset)
libfix = {}
for name in list(STD) + list(RECENTER):
    try:
        lf = p.FootprintLoad(lib, name)
    except Exception:
        lf = None
    if lf is None:
        continue
    what = fix(lf)
    p.FootprintSave(lib, lf)
    libfix[name] = [(m.m_Filename, (m.m_Rotation.x, m.m_Rotation.y, m.m_Rotation.z),
                     (m.m_Offset.x, m.m_Offset.y, m.m_Offset.z)) for m in lf.Models()]
    print(f"libreria {name:26s} {what}")

# scheda: stessi parametri della libreria
b = p.LoadBoard(path)
for f in b.GetFootprints():
    name = f.GetFPID().GetLibItemName().wx_str()
    if name not in libfix:
        continue
    ms = f.Models()
    ms.clear()
    for fn, r, o in libfix[name]:
        m = p.FP_3DMODEL()
        m.m_Filename = fn
        m.m_Rotation = p.VECTOR3D(*r)
        m.m_Offset = p.VECTOR3D(*o)
        ms.push_back(m)
    print(f"scheda   {f.GetReference():14s} {name}")
p.SaveBoard(path, b)
print("salvato")
