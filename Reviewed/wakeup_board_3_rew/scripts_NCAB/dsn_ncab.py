"""Riscrive il DSN esportato da KiCad con le regole NCAB/fabbricante per Freerouting.
- via ammessi: solo il passante 0.45/0.20, pubblicato come padstack gonfiato Ø0.60
  (nome "Via[0-13]_600:200_um": KiCad al reimport legge il foro 0.20 dal nome)
- microvia e via 0.50/0.25 esistenti restano nel wiring (fix) ma non sono usabili
Uso: python dsn_ncab.py in.dsn out.dsn
"""
import re, sys
s = open(sys.argv[1], encoding='utf8').read()
OLD, NEW = '"Via[0-13]_450:200_um"', '"Via[0-13]_600:200_um"'
# 1) elenco via della structure: solo il via NCAB gonfiato
s, n1 = re.subn(r'\(via "Via\[0-13\]_450:200_um"[^)\n]*\)', f'(via {NEW})', s, count=1)
# 2) padstack gonfiato in library (copia del 450 con cerchi da 600)
m = re.search(r'\n(\s*)\(padstack "Via\[0-13\]_450:200_um"(.*?)\n\1\)', s, re.S)
ps = m.group(0).replace(OLD, NEW)
ps = re.sub(r'\(circle (\S+) 450\)', r'(circle \1 600)', ps)
s = s[:m.end()] + ps + s[m.end():]
# 3) le net class usano il via gonfiato
s, n3 = re.subn(r'\(use_via "Via\[0-13\]_450:200_um"\)', f'(use_via {NEW})', s)
open(sys.argv[2], 'w', encoding='utf8').write(s)
print(f"structure via: {n1}, padstack aggiunto, classi aggiornate: {n3}")
