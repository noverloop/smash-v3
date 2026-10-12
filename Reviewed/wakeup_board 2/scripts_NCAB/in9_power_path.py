"""wakeup_board - In9.Cu power path: zone separate BAT_RAW / BAT_PROT / REG_IN_MAIN / BOOST_OUT.

Le quattro net hanno pad sparsi su tutta la scheda: In9 viene diviso con un diagramma
di Voronoi (ogni punto del disco R16.5 va alla net del pad piu vicino), celle raster
0.2 mm unite per net. Le zone di net diverse restano separate dal clearance di zona.
Uso: python.exe in9_power_path.py <board.kicad_pcb>
"""
import sys, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
b = p.LoadBoard(path)
NETS = ["BAT_RAW", "BAT_PROT", "REG_IN_MAIN", "BOOST_OUT"]
R = 16.5            # come gli altri piani: 0.5 mm dal bordo
G = 0.2             # passo raster

if any(z.GetFirstLayer() == p.In9_Cu for z in b.Zones()):
    sys.exit("In9 ha gia delle zone: niente fatto")

seeds = []
for f in b.GetFootprints():
    for pd in f.Pads():
        if pd.GetNetname() in NETS:
            seeds.append((tomm(pd.GetPosition().x), tomm(pd.GetPosition().y), pd.GetNetname()))
print("pad del power path:", collections.Counter(s[2] for s in seeds))

# raster Voronoi
n = int(math.ceil(2 * R / G))
owner = {}
for iy in range(n):
    y = -R + (iy + 0.5) * G
    for ix in range(n):
        x = -R + (ix + 0.5) * G
        if x * x + y * y > R * R:
            continue
        owner[(ix, iy)] = min(seeds, key=lambda s: (s[0] - x) ** 2 + (s[1] - y) ** 2)[2]

# rettangoli per righe (run-length) -> poligono per net
polys = {net: p.SHAPE_POLY_SET() for net in NETS}
for iy in range(n):
    ix = 0
    while ix < n:
        net = owner.get((ix, iy))
        if net is None:
            ix += 1
            continue
        j = ix
        while j + 1 < n and owner.get((j + 1, iy)) == net:
            j += 1
        x0, x1 = -R + ix * G, -R + (j + 1) * G
        y0, y1 = -R + iy * G, -R + (iy + 1) * G
        ch = p.SHAPE_LINE_CHAIN()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ch.Append(mm(x), mm(y))
        ch.SetClosed(True)
        polys[net].AddOutline(ch)
        ix = j + 1

# disco R16.5 per ritagliare la scaletta del raster sul bordo
disk = p.SHAPE_POLY_SET()
ch = p.SHAPE_LINE_CHAIN()
for k in range(96):
    a = 2 * math.pi * k / 96
    ch.Append(mm(R * math.cos(a)), mm(R * math.sin(a)))
ch.SetClosed(True)
disk.AddOutline(ch)

for net in NETS:
    ps = polys[net]
    ps.Simplify()
    ps.BooleanIntersection(disk)
    ps.Simplify()
    z = p.ZONE(b)
    z.SetLayer(p.In9_Cu)
    z.SetNet(b.FindNet(net))
    z.SetZoneName(f"PWRPATH_In9_{net}")
    z.SetAssignedPriority(0)
    z.SetLocalClearance(mm(0.15))
    z.SetMinThickness(mm(0.15))
    z.SetPadConnection(p.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.5)); z.SetThermalReliefSpokeWidth(mm(0.5))
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_AREA)
    z.SetMinIslandArea(int(mm(1.0)) * int(mm(1.0)) * 2)      # 2 mm2
    z.Outline().RemoveAllContours()
    for k in range(ps.OutlineCount()):
        z.Outline().AddOutline(ps.Outline(k))
    b.Add(z)
    print(f"  {net:12s} contorni {ps.OutlineCount():2d}  area {ps.Area() / 1e12:6.1f} mm2")

b.SetLayerType(p.In9_Cu, p.LT_POWER)
p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)
print("In9 -> power, zone create e riempite")
