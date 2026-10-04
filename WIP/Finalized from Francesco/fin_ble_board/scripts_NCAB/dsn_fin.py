"""DSN della fin_ble_board per Freerouting 2.4.1, con le regole NCAB. Va eseguito con il Python di KiCad.

- via ammessi: solo il passante 0.45/0.20, pubblicato gonfiato a 0.60 (emula FAB via-pista 0.15 e via-via 0.25)
- l'area regola "BGA_G0B1_FIN" (serve solo alle regole 0.08 della DRC) viene esportata da KiCad come keepout
  su tutti gli strati: il keepout viene tolto, altrimenti Freerouting non raggiunge il fanout
- componenti sul lato back: KiCad e Freerouting 2.4.1 non concordano su specchio/rotazione (piazzole
  scambiate su alcuni componenti ruotati). Ogni componente back viene riscritto come componente "front"
  a 0 gradi con un'immagine propria: pin nelle posizioni vere lette dalla scheda, padstack su B.Cu.
  Nessuna trasformazione resta da interpretare. (Al reimport i componenti vengono comunque ripristinati.)
Uso: python.exe dsn_fin.py <board.kicad_pcb> in.dsn out.dsn
"""
import re, sys
import pcbnew as p

tomm = p.ToMM
board, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
b = p.LoadBoard(board)
s = open(src, encoding="utf8").read()

# ---- via NCAB gonfiato
OLD, NEW = '"Via[0-13]_450:200_um"', '"Via[0-13]_600:200_um"'
s, n1 = re.subn(r'\(via "Via\[0-13\]_450:200_um"[^)\n]*\)', f'(via {NEW})', s, count=1)
m = re.search(r'\n(\s*)\(padstack "Via\[0-13\]_450:200_um"(.*?)\n\1\)', s, re.S)
ps = re.sub(r'\(circle (\S+) 450\)', r'(circle \1 600)', m.group(0).replace(OLD, NEW))
s = s[:m.end()] + ps + s[m.end():]
s, n3 = re.subn(r'\(use_via "Via\[0-13\]_450:200_um"\)', f'(use_via {NEW})', s)
# anche le via passanti gia posate (fanout, via ai piani) vengono pubblicate gonfiate: Freerouting ne sta a 0.15
s, n6 = re.subn(r'\(via "Via\[0-13\]_450:200_um"(\s+[-\d.])', r'(via "Via[0-13]_600:200_um"', s)

# ---- keepout dell'area BGA (poligoni a livello di structure); restano quelli dei fori nelle image
s, nk = re.subn(r'\n\s*\(keepout "" \(polygon [^\n]*\)\)', '', s)

# ---- componenti back -> immagini esplicite su B.Cu
def block(text, head):
    """blocco s-expr che inizia con head (indice di inizio, fine)"""
    i = text.find(head)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return i, j + 1
    return None

# immagine e padstack di ogni pin nell'export originale
images = {}
for mm_ in re.finditer(r'\(image (\S+)\n', s):
    name = mm_.group(1)
    bi, bj = block(s, "(image %s\n" % name)
    pins = {}
    for pm in re.finditer(r'\(pin (\S+) (?:\(rotate ([-\d.]+)\) )?("[^"]+"|\S+) ([-\d.]+) ([-\d.]+)\)', s[bi:bj]):
        pins[pm.group(3).strip('"')] = pm.group(1)
    images[name.strip('"')] = pins

placement = {}
for cm in re.finditer(r'\(component (\S+)\n((?:\s*\(place [^\n]*\n)+)', s):
    for pm in re.finditer(r'\(place (\S+) [-\d.]+ [-\d.]+ (front|back) ', cm.group(2)):
        placement[pm.group(1)] = (cm.group(1).strip('"'), pm.group(2))

F = {f.GetReference(): f for f in b.GetFootprints()}
tmp = 0
for f in b.GetFootprints():                       # stessi riferimenti temporanei dell'export
    if not f.GetReference().strip():
        tmp += 1
        F["MH_POT%d" % tmp] = f

new_ps, new_img, moved = {}, [], []
for ref, (img, side) in placement.items():
    if side != "back":
        continue
    f = F[ref]
    fx, fy = tomm(f.GetPosition().x) * 1000, -tomm(f.GetPosition().y) * 1000
    lines = []
    for q in f.Pads():
        num = q.GetNumber()
        if num not in images[img]:
            continue
        psn = images[img][num].strip('"')
        psb = psn + "_B"
        if psb not in new_ps:
            bi, bj = block(s, '(padstack "%s"' % psn) or block(s, "(padstack %s\n" % psn)
            txt = s[bi:bj]
            txt = txt.replace('"%s"' % psn, '"%s"' % psb, 1) if '"%s"' % psn in txt else txt.replace(psn, psb, 1)
            new_ps[psb] = txt.replace("F.Cu", "B.Cu")
        x = tomm(q.GetPosition().x) * 1000 - fx
        y = -tomm(q.GetPosition().y) * 1000 - fy
        ang = q.GetOrientation().AsDegrees() % 360
        rot = "(rotate %g) " % ang if abs(ang) > 1e-6 else ""
        lines.append('      (pin %s %s%s %.1f %.1f)' % (psb, rot, num, x, y))
    new_img.append('    (image "BK_%s"\n%s\n    )' % (ref, "\n".join(lines)))
    moved.append(ref)

# rimuove le righe place dei componenti back dai loro component, aggiunge component BK_*
for ref in moved:
    s = re.sub(r'\n\s*\(place %s [-\d.]+ [-\d.]+ back [^\n]*' % re.escape(ref), '', s, count=1)
s = re.sub(r'\n\s*\(component \S+\n(?=\s*\(component|\s*\)\s*\n\s*\(library)', '\n', s)   # component rimasti vuoti
pl_end = block(s, "(placement")[1] - 1
comps = "".join('\n    (component "BK_%s"\n      (place %s %.1f %.1f front 0)\n    )' % (
    r, r, tomm(F[r].GetPosition().x) * 1000, -tomm(F[r].GetPosition().y) * 1000) for r in moved)
s = s[:pl_end] + comps + "\n  " + s[pl_end:]
lib_i = block(s, "(library")[0] + len("(library")
s = s[:lib_i] + "\n" + "\n".join(new_img) + "\n" + "\n".join("    " + t for t in new_ps.values()) + s[lib_i:]

open(dst, "w", encoding="utf8").write(s)
print("via NCAB: %d, classi: %d, via esistenti gonfiate: %d, keepout BGA tolti: %d, componenti back riscritti: %d, padstack B.Cu: %d"
      % (n1, n3, n6, nk, len(moved), len(new_ps)))
