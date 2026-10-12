"""fin_ble_board: regole NCAB (Board Setup + net class) e piani interni. API pcbnew KiCad 10.
Stessa impostazione della wakeup_board: massa su In1/In4/In7/In10/In12, piani di potenza fra le masse,
le linee di potenza che attraversano la scheda (BAT_RAW, BAT_PROT, COMP_5V, 3V3_AON da J a P) hanno i pad
intercalati sull'anello: un unico strato diviso non le collega senza incroci, vanno sbrogliate a piste larghe (POWER).
Uso: python.exe setup_fin_ncab.py <board.kicad_pcb>
"""
import sys, math, collections
import pcbnew as p

mm, tomm = p.FromMM, p.ToMM
path = sys.argv[1]
b = p.LoadBoard(path)
if any(z.GetZoneName().startswith("PLANE_") for z in b.Zones()):
    sys.exit("piani gia presenti: niente fatto")

# --- Board Setup > Constraints (minimi assoluti NCAB, come wakeup/aft_end)
ds = b.GetDesignSettings()
ds.m_MinClearance = mm(0.08); ds.m_TrackMinWidth = mm(0.08); ds.m_MinConn = mm(0.08)
ds.m_ViasMinAnnularWidth = mm(0.075); ds.m_ViasMinSize = mm(0.25)
ds.m_HoleClearance = mm(0.10); ds.m_CopperEdgeClearance = mm(0.30)
ds.m_MinThroughDrill = mm(0.20); ds.m_HoleToHoleMin = mm(0.15)
ds.m_MicroViasMinSize = mm(0.25); ds.m_MicroViasMinDrill = mm(0.10)
ds.SetBoardThickness(mm(1.6))

# --- Net class
ns = ds.m_NetSettings
def setup_class(nc, cl, tw, vd, vh):
    nc.SetClearance(mm(cl)); nc.SetTrackWidth(mm(tw))
    nc.SetViaDiameter(mm(vd)); nc.SetViaDrill(mm(vh))
    nc.SetuViaDiameter(mm(0.25)); nc.SetuViaDrill(mm(0.10))
setup_class(ns.GetDefaultNetclass(), 0.10, 0.10, 0.45, 0.20)
CLASSES = {
    "POWER": (0.10, 0.25, 0.45, 0.20, ["FLEX_GND", "3V3", "3V3_AON", "COMP_5V", "COMP_5V_RAW",
                                       "BAT_RAW", "BAT_PROT", "BAT_CELL*"]),
    # uscite dei DRV8428E verso i motori (attraverso P): correnti di bobina
    "MOTOR": (0.10, 0.30, 0.45, 0.20, ["FIN?_AOUT?", "FIN?_BOUT?"]),
}
for name, (cl, tw, vd, vh, pats) in CLASSES.items():
    ns.SetNetclass(name, p.NETCLASS(name))
    setup_class(ns.GetNetClassByName(name), cl, tw, vd, vh)
    for pat in pats:
        ns.SetNetclassPatternAssignment(pat, name)
ns.ClearAllCaches()
b.SynchronizeNetsAndNetClasses(False)

R = 16.5   # piani a 0.5 mm dal bordo del disco R17 (NCAB chiede 0.30)
def disk():
    s = p.SHAPE_POLY_SET(); ch = p.SHAPE_LINE_CHAIN()
    for k in range(128):
        a = 2 * math.pi * k / 128
        ch.Append(mm(R * math.cos(a)), mm(R * math.sin(a)))
    ch.SetClosed(True); s.AddOutline(ch); return s

def add_zone(layer, net, name, poly, conn):
    z = p.ZONE(b)
    z.SetLayer(layer); z.SetNet(b.FindNet(net)); z.SetZoneName(name)
    z.SetAssignedPriority(0)
    z.SetLocalClearance(mm(0.20)); z.SetMinThickness(mm(0.10))
    z.SetPadConnection(conn)
    z.SetThermalReliefGap(mm(0.20)); z.SetThermalReliefSpokeWidth(mm(0.25))
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_AREA)
    z.SetMinIslandArea(int(mm(1.0)) * int(mm(1.0)) * 2)
    z.Outline().RemoveAllContours()
    for k in range(poly.OutlineCount()):
        z.Outline().AddOutline(poly.Outline(k))
    b.Add(z)
    return z

# --- piani pieni
PLANES = [
    (p.In1_Cu,  "FLEX_GND"),     # riferimento dei componenti TOP, pad termici dei DRV8428E
    (p.In2_Cu,  "COMP_5V_RAW"),  # VM dei 4 driver
    (p.In4_Cu,  "FLEX_GND"),
    (p.In6_Cu,  "3V3"),          # STM32G0B1, hall, pull-up
    (p.In7_Cu,  "FLEX_GND"),
    (p.In10_Cu, "FLEX_GND"),
    (p.In12_Cu, "FLEX_GND"),     # riferimento dei componenti BOTTOM
]
for layer, net in PLANES:
    conn = p.ZONE_CONNECTION_FULL if net == "FLEX_GND" else p.ZONE_CONNECTION_THERMAL
    add_zone(layer, net, "PLANE_%s_%s" % (b.GetLayerName(layer).replace(".", "_"), net), disk(), conn)

for layer in sorted({l for l, _ in PLANES}):
    b.SetLayerType(layer, p.LT_POWER)
p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)
print("\nzone create:")
for z in b.Zones():
    print("  %-30s %-8s %-12s area riempita %6.1f mm2" % (z.GetZoneName(), b.GetLayerName(z.GetLayer()), z.GetNetname(), z.GetFilledArea() / 1e12))
print("\nnet class:")
for name in ("Default", "POWER", "MOTOR"):
    nc = ns.GetNetClassByName(name)
    print("  %-8s clearance %.2f  pista %.2f  via %.2f/%.2f" % (name, tomm(nc.GetClearance()), tomm(nc.GetTrackWidth()), tomm(nc.GetViaDiameter()), tomm(nc.GetViaDrill())))
