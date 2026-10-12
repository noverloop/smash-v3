# aft_end_board – Regole di layout NCAB, net class e piani di alimentazione

*11-09-2026 · KiCad 10.0.3 · progetto `G:\civil_robot\aft_end_board`*

---

## 1. Scopo e fonti

- **Fonte delle regole:** `G:\PCB Info Sheet.docx`, il foglio Smash Electronics per NCAB del 27-08-2026 (richiesta S. de Boer, PCB "Compute Module"). Contiene i requisiti di fabbricazione, lo stackup a 14 layer (Appendix A), i tipi di via (Appendix B), le impedenze (Appendix C) e l'uso dei layer secondo ST (Appendix D).
- **Obiettivo:**
  1. tradurre il foglio in un file di regole KiCad (`.kicad_dru`);
  2. applicarlo al progetto `aft_end_board` (14 layer);
  3. creare i piani di alimentazione interni;
  4. preparare la scheda per l'autorouting con Freerouting.

---

## 2. Parametri principali dal PCB Info Sheet

| Parametro | Valore |
|---|---|
| Layer rame | 14, stackup non standard |
| Spessore finito | 1,6 – 2,0 mm |
| Materiale | FR4 high-Tg (Isola 370HR, IT180A…) |
| Rame esterno / interno | 0,5 oz – 18 µm |
| Foratura meccanica minima PTH/NPTH | 200 µm |
| Foro laser minimo | 100 µm |
| Pista minima | 100 µm (80 µm in alcuni punti) |
| Isolamento minimo | 80 µm tra i pad dei BGA a passo 0,5 mm |
| Via interrati | 2-13 (preferito), 3-12 · foro 0,2 / pad 0,45 mm |
| Microvia | 1-2, 2-3, 12-13, 13-14 · 250 µm / 100 µm |
| Riempimento via | passanti resin filled · via-in-pad → VIPPO · microvia riempiti di rame e capped |
| Impedenza controllata | sì, su layer esterni e interni (vedi Appendix C) |
| Solder mask | nero, Top e Bottom |
| Serigrafia | **no**, né Top né Bottom |
| Finitura | ENIG / HAL lead-free · oro galvanico full-surface: sì |
| Contorno | fresato, fresature interne ammesse, niente V-scoring |
| Classe | IPC Classe 3 · RoHS · lead-free reflow · test elettrico |
| Marcature | UL + logo, date code, logo del produttore |

**Impedenze (Appendix C), tutte ±10 %**

| Impedenza | Struttura | Layer |
|---|---|---|
| 55 Ω | single ended microstrip e coplanare | Top e Bottom |
| 90 Ω | differenziale microstrip | Top e Bottom |
| 100 Ω | differenziale microstrip / stripline | Top / interni |
| 120 Ω | differenziale microstrip / stripline | Top e Bottom / interni |

**Mappatura dei layer dal documento a KiCad:**
1 = `F.Cu`, 2 = `In1.Cu`, 3 = `In2.Cu`, … 12 = `In11.Cu`, 13 = `In12.Cu`, 14 = `B.Cu`

---

## 3. File di regole `NCAB_14L_HDI.kicad_dru`

- **Master:** `G:\civil_robot\NCAB_14L_HDI.kicad_dru`
- **Copia nel progetto:** `aft_end_board\aft_end_board.kicad_dru`, caricata in automatico da KiCad.
- **Versione:** pensato per KiCad 10. Per usarlo su KiCad 9 bisogna togliere la keyword `blind_via`.

### 3.1 Regole

Nella colonna Fonte: **DOC** = valore preso dal PCB Info Sheet; **ASS** = valore assunto (tipico HDI / IPC classe 3), **da confermare con NCAB**.

| Regola | Valore | Fonte |
|---|---|---|
| Larghezza pista minima | 0,10 mm | DOC |
| Fan-out BGA 0,5 mm: pista e isolamento | 0,08 mm, solo dentro Rule Area `BGA*` | DOC |
| Rame dal contorno fresato | 0,30 mm | ASS |
| Foro meccanico minimo (PTH, NPTH, via) | 0,20 mm | DOC |
| Microvia: foro / pad / anello | 0,10 (max 0,15) / 0,25 / 0,075 mm | DOC (max: ASS) |
| Via passanti e interrati: pad / anello | 0,45 / 0,125 mm | DOC |
| Anello dei pad PTH | 0,125 mm | ASS |
| Rame-foro, fori meccanici | 0,20 mm | ASS |
| Rame-foro, microvia verso piste e zone | 0,10 mm | ASS |
| Foro-foro, fori meccanici | 0,25 mm | ASS |
| Foro-foro, microvia | 0,15 mm | ASS |
| Span dei microvia ammessi | 1-2, 2-3, 12-13, 13-14 (gli altri: errore) | DOC |
| Span dei via meccanici ammessi | 1-14, 2-13, 3-12 (niente blind meccanici) | DOC |
| Impedenze 55/90/100/120 Ω | solo modelli commentati, da completare | DOC |

**Uso della deroga BGA:** disegnare sopra il BGA una Rule Area su tutti i layer rame, senza spuntare nessun keepout, con un nome che inizia per `BGA` (per esempio `BGA_U1`). La deroga prevale anche sui clearance più grandi delle net class.

**Clearance generale:** il valore di 0,10 mm va impostato nella net class Default e **non** nel `.dru`. Una regola custom senza condizione annullerebbe i clearance più grandi delle altre net class.

### 3.2 Verifica del file di regole

Ho generato con l'API Python di KiCad 10 una scheda di test a 14 layer con elementi validi e non validi, poi ho lanciato `kicad-cli pcb drc`.

| Caso di test | Esito atteso | Esito |
|---|---|---|
| Via passante 0,20/0,45 | OK | ✅ |
| Via passante 0,15/0,40 | errore su foro e diametro | ✅ |
| Via interrati 2-13 e 3-12 | OK | ✅ |
| Via interrato 4-11 | errore di span | ✅ |
| Via blind meccanico 1-3 | errore di span | ✅ |
| Microvia 1-2, 13-14 e 2-3 impilato su 1-2 | OK | ✅ |
| Microvia 3-4 | errore di span | ✅ |
| Microvia con pad 0,20 mm | errore su diametro e anello | ✅ |
| Microvia con foro 0,20 mm | errore su foro massimo | ✅ |
| Pista da 0,09 mm fuori BGA | errore | ✅ |
| Pista da 0,08 mm e gap da 0,085 mm dentro `BGA_U1` | OK (prevale sulla net class) | ✅ |
| Gap da 0,085 mm fuori BGA | errore | ✅ |
| Pista a 0,20 mm dal bordo | errore | ✅ |
| Fori meccanici a 0,20 mm di distanza | avviso foro-foro | ✅ |
| Layer interno rinominato (`In1.Cu` → `L2_GND`) | le regole sugli span funzionano ancora | ✅ |

---

## 4. Applicazione al progetto aft_end_board

### 4.1 Stato iniziale

- Scheda tonda Ø34 mm, 14 layer. In1, In2, In11 e In12 erano già di tipo "power".
- 91 componenti, 83 net, nessuna pista e nessuna zona.
- Le regole del progetto erano sotto i limiti NCAB: clearance 0,075 mm, via 0,30/0,15 mm, foro microvia 0,15 mm.
- Con le regole NCAB il piazzamento **non ha violazioni di rame**.

### 4.2 Metodo

Konnect MCP non era collegato alla sessione di Claude Code. Per questo:

1. KiCad è stato chiuso.
2. Le modifiche sono state fatte con l'**API Python ufficiale di KiCad 10** (`pcbnew`), che usa lo stesso motore di salvataggio di KiCad. Nessuna modifica testuale dei file.
3. Lo script è stato collaudato prima su una copia nello scratchpad, poi applicato al progetto.

- **Backup degli originali:** `aft_end_board\backup_pre_NCAB_20260911_111134\` (`.kicad_pcb`, `.kicad_pro`, `.kicad_prl`).
- **Lock rimasti:** i file `~*.lck` del mattino (con KiCad già chiuso) bloccavano il salvataggio del `.kicad_pro`. Li ho eliminati; KiCad li ricrea da solo.

### 4.3 Board Setup → Constraints

| Vincolo | Valore |
|---|---|
| Minimum clearance | 0,08 mm |
| Minimum track width | 0,08 mm |
| Minimum connection width | 0,08 mm |
| Minimum annular width | 0,075 mm |
| Minimum via diameter | 0,25 mm |
| Copper to hole clearance | 0,10 mm |
| Copper to edge clearance | 0,30 mm |
| Minimum through hole | 0,20 mm |
| Hole to hole clearance | 0,15 mm |
| Minimum µVia diameter / hole | 0,25 / 0,10 mm |

Questi sono i minimi assoluti: le regole custom del `.dru` alzano i valori dove serve.

### 4.4 Net class

| Classe | Net | Clearance | Pista | Via | µVia |
|---|---|---|---|---|---|
| Default | tutte le altre | 0,10 | 0,10 | 0,45 / 0,20 | 0,25 / 0,10 |
| POWER | FLEX_GND, BAT_RAW, BAT_PROT, 3V3, 3V3_AON, COMP_5V | 0,10 | 0,25 | 0,45 / 0,20 | 0,25 / 0,10 |
| FIRE | FIRE_HV, FIRE_ARMED, ACT_WIRE_* | 0,10 | 0,40 | 0,60 / 0,30 | 0,25 / 0,10 |

Le assegnazioni sono fatte per pattern di nome net (Board Setup → Net Classes).

### 4.5 Piani di alimentazione

| Layer | Net | Zona |
|---|---|---|
| In1.Cu | FLEX_GND | `PLANE_In1_Cu_FLEX_GND` |
| In2.Cu | BAT_PROT | `PLANE_In2_Cu_BAT_PROT` |
| In11.Cu | 3V3 | `PLANE_In11_Cu_3V3` |
| In12.Cu | FLEX_GND | `PLANE_In12_Cu_FLEX_GND` |

Impostazioni comuni a tutte le zone:

- contorno quadrato ±18 mm, ritagliato sul cerchio Ø34 a 0,3 mm dal bordo (875,8 mm² di rame per piano);
- clearance 0,20 mm, spessore minimo 0,10 mm;
- thermal relief con gap 0,20 mm e razze da 0,25 mm;
- rimozione delle isole sotto 2 mm², così prima del routing i piani restano visibili.

**Scelta progettuale:** FIRE_HV, FIRE_ARMED, COMP_5V, 3V3_AON e BAT_RAW restano piste larghe e non piani, per non estendere il bus di sparo su tutta la scheda. In1 e In12 fanno da riferimento di massa per Top e Bottom.

### 4.6 DRC dopo le modifiche (prima del routing)

- **Errori:** 0
- **Avvisi:** 41 di serigrafia (testi da 0,45 mm; il foglio NCAB prevede niente serigrafia) e 4 "isolated copper" (piani non ancora collegati da via).
- **Connessioni da sbrogliare:** 183.

---

## 5. Freerouting

**Procedura**

1. Riaprire KiCad e lanciare il plugin Freerouting.
2. Usare i via delle net class, senza microvia né via interrati: il file DSN esportato da KiCad non li gestisce.
3. I layer "power" In1, In2, In11 e In12 sono trattati come piani. Il routing avviene sugli altri 10 layer e i piani si collegano con via passanti.
4. Al rientro in KiCad premere **B** per riempire di nuovo le zone, salvare e lanciare il DRC.

**Dopo il routing**

- Controllare la distanza di 0,30 mm dal bordo e le connessioni rimaste aperte.
- Aggiungere una colata FLEX_GND su F.Cu e B.Cu, con via di cucitura verso In1 e In12.
- Rifare il DRC.

### 5.1 Esito del routing (Freerouting v2.3.0)

- **Risultato:** 1225 segmenti e 183 via passanti, **0 connessioni aperte**.
- **Backup della scheda appena sbrogliata:** `aft_end_board\backup_post_freerouting_20260911_125953\`.

Il DRC NCAB ha trovato 8 errori e 1 avviso, corretti con lo script `fix_routed.py` (API pcbnew):

| Problema | Correzione |
|---|---|
| 2 via FIRE (ACT_WIRE_3, ACT_WIRE_9) con pad 0,45 e foro 0,30: anello di 0,075 mm | foro portato a 0,20 mm (anello 0,125) |
| Via ACT_WIRE_3 a 0,196 mm dal pad 21 di J (minimo 0,20) | risolto dallo stesso cambio di foro |
| 4 piste da 0,075 mm su ACTIVATE_CONFIRM e SYS_SPI_MOSI, sotto il minimo assoluto di 0,08 | allargate a 0,10 mm |
| Ramo morto di GPIO_EXT_3 su F.Cu (3 segmenti) | rimosso |

**DRC finale:** 0 errori, 0 connessioni aperte, zone riempite. Restano solo 41 avvisi di serigrafia, che non viene prodotta.

**Nota sulle strozzature:** in alcuni punti Freerouting ha ristretto le piste di potenza, per esempio FIRE a 0,20–0,30 mm e POWER a 0,187 mm. Le regole sono rispettate (minimo 0,10), ma in quei tratti la portata di corrente è più bassa.

### 5.2 File di produzione: `aft_end_board\fab_NCAB_20260911\`

| File | Contenuto |
|---|---|
| `*-F_Cu.gtl`, `*-In1_Cu.g1` … `*-In12_Cu.g12`, `*-B_Cu.gbl` | 14 layer rame, Gerber X2 |
| `*-F_Mask.gts`, `*-B_Mask.gbs` | solder mask (nero, da specificare nell'ordine) |
| `*-F_Paste.gtp`, `*-B_Paste.gbp` | pasta saldante, per lo stencil |
| `*-Edge_Cuts.gm1` | contorno fresato, Ø34 mm |
| `*-job.gbrjob` | job file: 14 layer, 34,15 × 34,15 mm, 1,6 mm, ENIG |
| `*-PTH.drl`, `*-NPTH.drl` | forature Excellon in mm: 146 fori da 0,20 e 37 da 0,30 (NPTH vuoto) |
| `*-PTH-drl_map.pdf`, `*-NPTH-drl_map.pdf` | mappe delle forature |
| `*-drill_report.txt` | rapporto forature |
| `aft_end_board.d356` | netlist IPC-D-356 per il test elettrico |
| `aft_end_board-DRC_NCAB.rpt` | rapporto DRC finale |
| `aft_end_board_NCAB_fab_20260911.zip` | tutti i file sopra, da inviare a NCAB |

La serigrafia F.SilkS e B.SilkS è **esclusa**, come indica il PCB Info Sheet ("Top/Bottom silkscreen: No").

**Da indicare nell'ordine a NCAB** (non ricavabile dai Gerber):

- solder mask nero;
- via passanti resin filled;
- IPC Classe 3, marcatura UL, date code;
- stackup e spessore finale;
- test elettrico sul file IPC-D-356.

---

## 6. Punti aperti

**Da chiarire con NCAB**

- [ ] Spessore del rame: il foglio indica 18 µm (0,5 oz), l'immagine dello stackup 35 µm (1 oz). Cambia le larghezze per l'impedenza.
- [ ] L'Appendix B mostra anche microvia 6-7 e 9-8, assenti dalla tabella. Il `.dru` segue la tabella e li segnala come errore.
- [ ] Confermare i valori marcati **ASS**: bordo 0,30; rame-foro 0,20 / 0,10; foro-foro 0,25 / 0,15; foro laser max 0,15; anello dei pad PTH 0,125.
- [ ] Larghezze e gap delle piste a impedenza controllata, dal calcolo dello stackup NCAB. Poi completare i modelli nel `.dru`.

**Da verificare sul progetto**

- [ ] **FIRE_HV:** clearance lasciato a 0,10 mm perché R_FIRE_BLEED e R_FIRE_MON1 distano 0,101 mm. Se la tensione supera qualche decina di volt, vanno distanziate e il clearance della classe FIRE va alzato.
- [ ] **Larghezze FIRE e POWER** (0,40 e 0,25 mm): scelte senza conoscere le correnti di sparo. Da dimensionare, tenendo conto del rame da 18 µm.
- [ ] **U_FIRE_DEC (CD74HC4514):** VCC è su BAT_PROT e il massimo ammesso è 6 V. Verificare la tensione della batteria.
- [ ] **Stackup nel file:** è rimasto quello originale (1,6 mm, rame 17,5/35 µm), non la proposta NCAB. Aggiornarlo quando lo stackup è definitivo.
- [x] **Serigrafia:** il foglio NCAB dice "no", quindi i layer silk sono esclusi dai Gerber.
- [ ] **Stackup nel job file:** indica 1,6 mm, cioè quello del progetto. Allinearlo allo stackup NCAB prima dell'ordine.
- [ ] **Colata GND esterna:** la colata FLEX_GND su F.Cu e B.Cu, con via di cucitura, non è stata aggiunta. Farla prima dell'ordine definitivo, poi rigenerare i file.

---

## Appendice – Script usato (`apply_ncab_planes.py`)

Da lanciare con il Python di KiCad 10, **a KiCad chiuso** e **su una scheda senza zone `PLANE_*`**. Rieseguirlo su una scheda già elaborata fa fallire i binding Python: in quel caso ripartire dal backup.

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" apply_ncab_planes.py aft_end_board.kicad_pcb
```

```python
import sys
import pcbnew as p

mm = p.FromMM
path = sys.argv[1]
b = p.LoadBoard(path)
ds = b.GetDesignSettings()

# Board Setup > Constraints
ds.m_MinClearance = mm(0.08);  ds.m_TrackMinWidth = mm(0.08);  ds.m_MinConn = mm(0.08)
ds.m_ViasMinAnnularWidth = mm(0.075);  ds.m_ViasMinSize = mm(0.25)
ds.m_HoleClearance = mm(0.10);  ds.m_CopperEdgeClearance = mm(0.30)
ds.m_MinThroughDrill = mm(0.20);  ds.m_HoleToHoleMin = mm(0.15)
ds.m_MicroViasMinSize = mm(0.25);  ds.m_MicroViasMinDrill = mm(0.10)

# Net class
ns = ds.m_NetSettings
def setup_class(nc, clearance, track, via_d, via_h):
    nc.SetClearance(mm(clearance)); nc.SetTrackWidth(mm(track))
    nc.SetViaDiameter(mm(via_d)); nc.SetViaDrill(mm(via_h))
    nc.SetuViaDiameter(mm(0.25)); nc.SetuViaDrill(mm(0.10))

setup_class(ns.GetDefaultNetclass(), 0.10, 0.10, 0.45, 0.20)
classes = {
    "POWER": (0.10, 0.25, 0.45, 0.20, ["FLEX_GND", "BAT_RAW", "BAT_PROT", "3V3", "3V3_AON", "COMP_5V"]),
    "FIRE":  (0.10, 0.40, 0.60, 0.30, ["FIRE_HV", "FIRE_ARMED", "ACT_WIRE_*"]),
}
for name, (cl, tw, vd, vh, patterns) in classes.items():
    ns.SetNetclass(name, p.NETCLASS(name))
    setup_class(ns.GetNetClassByName(name), cl, tw, vd, vh)
    for pat in patterns:
        ns.SetNetclassPatternAssignment(pat, name)
ns.ClearAllCaches()
b.SynchronizeNetsAndNetClasses(False)

# Piani interni
PLANES = [(p.In1_Cu, "FLEX_GND"), (p.In2_Cu, "BAT_PROT"),
          (p.In11_Cu, "3V3"), (p.In12_Cu, "FLEX_GND")]
R = 18.0
for layer, netname in PLANES:
    z = p.ZONE(b)
    z.SetLayer(layer); z.SetNet(b.FindNet(netname))
    z.SetZoneName(f"PLANE_{b.GetLayerName(layer).replace('.', '_')}_{netname}")
    z.SetLocalClearance(mm(0.20)); z.SetMinThickness(mm(0.10))
    z.SetPadConnection(p.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.20)); z.SetThermalReliefSpokeWidth(mm(0.25))
    z.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_AREA)
    z.SetMinIslandArea(int(mm(1.0)) * int(mm(1.0)) * 2)   # 2 mm^2
    ol = z.Outline(); ol.NewOutline()
    for x, y in [(-R, -R), (R, -R), (R, R), (-R, R)]:
        ol.Append(mm(x), mm(y))
    b.Add(z)

p.ZONE_FILLER(b).Fill(b.Zones())
p.SaveBoard(path, b)   # salva anche il .kicad_pro (servono i lock ~*.lck assenti)
```

---

## File coinvolti

| File | Contenuto |
|---|---|
| `G:\civil_robot\NCAB_14L_HDI.kicad_dru` | regole NCAB, master |
| `aft_end_board\aft_end_board.kicad_dru` | copia usata dal progetto |
| `aft_end_board\aft_end_board.kicad_pcb` | piani In1, In2, In11, In12 |
| `aft_end_board\aft_end_board.kicad_pro` | Board Setup e net class |
| `aft_end_board\backup_pre_NCAB_20260911_111134\` | originali prima delle modifiche |
| `aft_end_board\backup_post_freerouting_20260911_125953\` | scheda sbrogliata, prima delle correzioni |
| `aft_end_board\fab_NCAB_20260911\` | Gerber, forature, IPC-D-356, DRC e zip per NCAB |
| `aft_end_board\scripts_NCAB\` | `apply_ncab_planes.py`, `fix_routed.py`, `export_fab.sh` |
| `aft_end_board\NCAB_regole_e_piani.md` | questo documento |
