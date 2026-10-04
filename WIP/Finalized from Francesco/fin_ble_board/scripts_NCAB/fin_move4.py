"""Porta dentro i cutout delle celle (margine >= 0.2 mm) i componenti bottom troppo vicini al bordo.
Sposta ogni componente lungo la retta verso il centro della sua cella, del minimo necessario,
controllando che il courtyard non tocchi quello di altri componenti bottom (esclusi i contatti cella).
Uso: python.exe fin_move4.py <board> [--apply]"""
import sys, math, pcbnew as p
tomm, mm = p.ToMM, p.FromMM
path=sys.argv[1]; APPLY="--apply" in sys.argv
b=p.LoadBoard(path)
CEL=[(0.0,-8.6),(7.45,4.3),(-7.45,4.3)]; R=7.60; M=0.20
REFS=["J_HALL_FIN_VCC","J_HALL_FIN_OUT","C_G0B1_FIN_BULK","C_FIN4_DVDD"]
F={f.GetReference():f for f in b.GetFootprints()}
def outline(f,dx=0,dy=0):
    pts=[]
    c=f.GetCourtyard(p.B_CrtYd)
    if c is not None and c.OutlineCount():
        o=c.Outline(0); pts+=[(tomm(o.CPoint(i).x)+dx,tomm(o.CPoint(i).y)+dy) for i in range(o.PointCount())]
    for q in f.Pads():
        cx,cy=tomm(q.GetPosition().x)+dx,tomm(q.GetPosition().y)+dy
        if q.GetShape()==p.PAD_SHAPE_CIRCLE:
            r=tomm(q.GetSize(p.B_Cu).x)/2; pts+=[(cx+r*math.cos(k*math.pi/18),cy+r*math.sin(k*math.pi/18)) for k in range(36)]
        else:
            bb=q.GetBoundingBox(); hx=(tomm(bb.GetRight())-tomm(bb.GetLeft()))/2; hy=(tomm(bb.GetBottom())-tomm(bb.GetTop()))/2
            pts+=[(cx+sx*hx,cy+sy*hy) for sx in(-1,1) for sy in(-1,1)]
    return pts
def margin(pts): return min(max(R-math.hypot(x-cx,y-cy) for cx,cy in CEL) for x,y in pts)
def box(pts): xs=[q[0] for q in pts]; ys=[q[1] for q in pts]; return min(xs),min(ys),max(xs),max(ys)
others={r:box(outline(f)) for r,f in F.items() if f.IsFlipped() and r not in REFS and not r.startswith(("P_fin","P_CELL"))}
moves={}
for r in REFS:
    f=F[r]; x0,y0=tomm(f.GetPosition().x),tomm(f.GetPosition().y)
    cx,cy=min(CEL,key=lambda c:math.hypot(x0-c[0],y0-c[1]))
    d=math.hypot(cx-x0,cy-y0); ux,uy=(cx-x0)/d,(cy-y0)/d
    m0=margin(outline(f)); best=None
    for k in range(0,81):
        s=k*0.025; dx,dy=ux*s,uy*s
        pts=outline(f,dx,dy)
        if margin(pts)<M: continue
        bx=box(pts)
        hit=[o for o,ob in others.items() if bx[0]<ob[2] and bx[2]>ob[0] and bx[1]<ob[3] and bx[3]>ob[1]]
        hit+=[o for o,(mx,my,ob) in moves.items() if bx[0]<ob[2] and bx[2]>ob[0] and bx[1]<ob[3] and bx[3]>ob[1]]
        if hit: continue
        best=(s,dx,dy,margin(pts),bx); break
    if best is None: print("%-16s margine %+.2f: NESSUNA posizione libera entro 2 mm"%(r,m0)); continue
    s,dx,dy,m1,bx=best
    moves[r]=(x0+dx,y0+dy,bx)
    print("%-16s (%6.2f,%6.2f) -> (%6.2f,%6.2f)  spostamento %.2f mm  margine %+.2f -> %+.2f"%(r,x0,y0,x0+dx,y0+dy,s,m0,m1))
if APPLY:
    for r,(x,y,_) in moves.items(): F[r].SetPosition(p.VECTOR2I(mm(x),mm(y)))
    p.ZONE_FILLER(b).Fill(b.Zones()); p.SaveBoard(path,b); print("salvato")
else: print("(prova: niente scritto)")
