"""wakeup_board: Board Setup NCAB, net class, tipo layer dei piani. API pcbnew KiCad 10."""
import sys, pcbnew as p
mm = p.FromMM
path = sys.argv[1]
b = p.LoadBoard(path)
ds = b.GetDesignSettings()
ds.m_MinClearance = mm(0.08); ds.m_TrackMinWidth = mm(0.08); ds.m_MinConn = mm(0.08)
ds.m_ViasMinAnnularWidth = mm(0.075); ds.m_ViasMinSize = mm(0.25)
ds.m_HoleClearance = mm(0.10); ds.m_CopperEdgeClearance = mm(0.30)
ds.m_MinThroughDrill = mm(0.20); ds.m_HoleToHoleMin = mm(0.15)
ds.m_MicroViasMinSize = mm(0.25); ds.m_MicroViasMinDrill = mm(0.10)
ds.SetBoardThickness(mm(1.6))

ns = ds.m_NetSettings
def setup_class(nc, cl, tw, vd, vh):
    nc.SetClearance(mm(cl)); nc.SetTrackWidth(mm(tw))
    nc.SetViaDiameter(mm(vd)); nc.SetViaDrill(mm(vh))
    nc.SetuViaDiameter(mm(0.25)); nc.SetuViaDrill(mm(0.10))
setup_class(ns.GetDefaultNetclass(), 0.10, 0.10, 0.45, 0.20)
ns.SetNetclass("POWER", p.NETCLASS("POWER"))
setup_class(ns.GetNetClassByName("POWER"), 0.10, 0.25, 0.45, 0.20)
for pat in ["BAT_RAW", "BAT_PROT", "REG_IN_MAIN", "BOOST_OUT", "BOOST_SW", "COMP_5V", "COMP_5V_RAW"]:
    ns.SetNetclassPatternAssignment(pat, "POWER")
ns.ClearAllCaches()
b.SynchronizeNetsAndNetClasses(False)

# layer con piano -> tipo "power" (Freerouting non ci sbroglia piste)
plane_layers = sorted({z.GetFirstLayer() for z in b.Zones() if not z.GetIsRuleArea() and z.GetFirstLayer() not in (p.F_Cu, p.B_Cu)})
for l in plane_layers:
    b.SetLayerType(l, p.LT_POWER)
p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)
print("piani su:", [b.GetLayerName(l) for l in plane_layers])
print("tipi:", [(b.GetLayerName(l), p.LAYER.ShowType(b.GetLayerType(l))) for l in p.LSET.AllCuMask(14).Seq()])
