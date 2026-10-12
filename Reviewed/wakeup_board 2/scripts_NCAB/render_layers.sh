#!/usr/bin/env bash
# Uso: render_layers.sh <board.kicad_pcb> <out.png>
set -e
K="/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"
PCB="$1"; OUT="$2"; D=$(dirname "$PCB")
cd "$D"
for L in F.Cu In3.Cu In5.Cu In8.Cu B.Cu; do
  "$K" pcb export svg -l "$L" --mode-single --fit-page-to-board --exclude-drawing-sheet -o "lay_${L//./_}.svg" "$(basename "$PCB")" >/dev/null 2>&1
done
python - <<'PY'
import re
def body(fn,color):
    s=open(fn,encoding='utf8').read(); s=s[s.index('<g'):s.rindex('</svg>')]
    s=re.sub(r'fill:#[0-9A-Fa-f]{6}','fill:'+color,s); return re.sub(r'stroke:#[0-9A-Fa-f]{6}','stroke:'+color,s)
lay=[('lay_F_Cu.svg','#e03030','F.Cu'),('lay_In3_Cu.svg','#30c0e0','In3.Cu'),('lay_In5_Cu.svg','#40d040','In5.Cu'),('lay_In8_Cu.svg','#e0c020','In8.Cu'),('lay_B_Cu.svg','#4060ff','B.Cu')]
cells=''.join(f'<div><div style="color:#ccc;font:13px sans-serif">{n}</div><svg xmlns="http://www.w3.org/2000/svg" width="380" height="380" viewBox="0 0 34 34" style="background:#000">{body(f,c)}</svg></div>' for f,c,n in lay)
allsvg=''.join(f'<g opacity="0.8">{body(f,c)}</g>' for f,c,n in lay)
html=f'<html><body style="margin:0;background:#111"><div style="display:flex;flex-wrap:wrap;gap:6px;width:1170px">{cells}<div><div style="color:#ccc;font:13px sans-serif">tutti i layer</div><svg xmlns="http://www.w3.org/2000/svg" width="380" height="380" viewBox="0 0 34 34" style="background:#000">{allsvg}</svg></div></div></body></html>'
open('view.html','w',encoding='utf8').write(html)
PY
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --hide-scrollbars --window-size=1180,830 --screenshot="$(cygpath -w "$D")\$(basename "$OUT")" "file:///$(cygpath -m "$D")/view.html" >/dev/null 2>&1
ls -la "$OUT"
