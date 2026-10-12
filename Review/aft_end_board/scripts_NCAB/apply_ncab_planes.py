"""Applica regole NCAB, net class e piani interni a una scheda KiCad 10.
Uso: python.exe apply_ncab_planes.py <board.kicad_pcb>
Usa solo l'API pcbnew di KiCad (nessuna modifica testuale dei file)."""
import sys
import pcbnew as p

mm = p.FromMM
path = sys.argv[1]
b = p.LoadBoard(path)
ds = b.GetDesignSettings()

# --- Board Setup > Constraints (minimi assoluti, vedi header del .kicad_dru)
ds.m_MinClearance = mm(0.08)
ds.m_TrackMinWidth = mm(0.08)
ds.m_MinConn = mm(0.08)
ds.m_ViasMinAnnularWidth = mm(0.075)
ds.m_ViasMinSize = mm(0.25)
ds.m_HoleClearance = mm(0.10)
ds.m_CopperEdgeClearance = mm(0.30)
ds.m_MinThroughDrill = mm(0.20)
ds.m_HoleToHoleMin = mm(0.15)
ds.m_MicroViasMinSize = mm(0.25)
ds.m_MicroViasMinDrill = mm(0.10)

# --- Net class
ns = ds.m_NetSettings

def setup_class(nc, clearance, track, via_d, via_h):
    nc.SetClearance(mm(clearance))
    nc.SetTrackWidth(mm(track))
    nc.SetViaDiameter(mm(via_d))
    nc.SetViaDrill(mm(via_h))
    nc.SetuViaDiameter(mm(0.25))
    nc.SetuViaDrill(mm(0.10))
    return nc

setup_class(ns.GetDefaultNetclass(), 0.10, 0.10, 0.45, 0.20)
classes = {
    "POWER": (0.10, 0.25, 0.45, 0.20,
              ["FLEX_GND", "BAT_RAW", "BAT_PROT", "3V3", "3V3_AON", "COMP_5V"]),
    "FIRE":  (0.10, 0.40, 0.60, 0.30,
              ["FIRE_HV", "FIRE_ARMED", "ACT_WIRE_*"]),
}
for name, (cl, tw, vd, vh, patterns) in classes.items():
    nc = ns.GetNetClassByName(name) if ns.HasNetclass(name) else None
    if nc is None or nc.GetName() != name:
        nc = p.NETCLASS(name)
        ns.SetNetclass(name, nc)
        nc = ns.GetNetClassByName(name)
    setup_class(nc, cl, tw, vd, vh)
    for pat in patterns:
        ns.SetNetclassPatternAssignment(pat, name)
ns.ClearAllCaches()
b.SynchronizeNetsAndNetClasses(False)

# --- Piani interni
PLANES = [
    (p.In1_Cu,  "FLEX_GND"),
    (p.In2_Cu,  "BAT_PROT"),
    (p.In11_Cu, "3V3"),
    (p.In12_Cu, "FLEX_GND"),
]
# rimuove eventuali piani creati da una esecuzione precedente
for z in list(b.Zones()):
    if z.GetZoneName().startswith("PLANE_"):
        b.Remove(z)

R = 18.0  # quadrato che contiene il contorno circolare D34; il fill viene ritagliato sul bordo
for layer, netname in PLANES:
    net = b.FindNet(netname)
    if net is None:
        sys.exit(f"net {netname} non trovata")
    z = p.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetZoneName(f"PLANE_{b.GetLayerName(layer).replace('.', '_')}_{netname}")
    z.SetAssignedPriority(0)
    z.SetLocalClearance(mm(0.20))
    z.SetMinThickness(mm(0.10))
    z.SetPadConnection(p.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.20))
    z.SetThermalReliefSpokeWidth(mm(0.25))
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_AREA)
    z.SetMinIslandArea(int(mm(1.0)) * int(mm(1.0)) * 2)  # 2 mm^2
    ol = z.Outline()
    ol.NewOutline()
    for x, y in [(-R, -R), (R, -R), (R, R), (-R, R)]:
        ol.Append(mm(x), mm(y))
    b.Add(z)

filler = p.ZONE_FILLER(b)
filler.Fill(b.Zones())

p.SaveBoard(path, b)

for z in b.Zones():
    print(f"{z.GetZoneName():32s} {b.GetLayerName(z.GetLayer()):8s} {z.GetNetname():10s} "
          f"filled={z.IsFilled()} area={z.GetFilledArea() / 1e12:.1f} mm2")
for name in ["Default", "POWER", "FIRE"]:
    nc = ns.GetNetClassByName(name)
    print(name, p.ToMM(nc.GetClearance()), p.ToMM(nc.GetTrackWidth()),
          p.ToMM(nc.GetViaDiameter()), p.ToMM(nc.GetViaDrill()))
