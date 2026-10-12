# wakeup_board — indice e stato del lavoro

Progetto: `G:\fin_ble and wakeup\wakeup_board`
Ultimo aggiornamento: **10/09/2026**

> **11/09/2026:** regole NCAB riviste (il `.dru` precedente aveva regole mai attive in KiCad 10),
> stackup NCAB ~1.6 mm, fanout HDI di U_WBA con microvia nel pad. Vedi
> `NCAB_REGOLE_FANOUT_wakeup_board.md`. Backup: `..\backup_pre_NCAB_fanout_20260911_173525\`.

## Documenti

| File | Contenuto |
|---|---|
| `NCAB_REGOLE_FANOUT_wakeup_board.md` | revisione del .dru, nuove regole, fanout di U_WBA, stackup NCAB, punti aperti |
| `STATO_wakeup_board.md` | architettura, i 6 problemi trovati nella netlist, regole NCAB |
| `PIANI_wakeup_board.md` | schema dei 14 layer, gli 8 piani creati, la ricetta per le board smash |
| `wakeup_board_schematico.svg` | schematico ricostruito dalla netlist del PCB |
| `wakeup_board_TOP.svg` | placement lato componenti (30 pezzi) |
| `wakeup_board_BOTTOM.svg` | placement lato saldature (84 pezzi), vista specchiata |
| `wakeup_board_placement.svg` | le due viste affiancate |

Datasheet in `..\datasheets\`: STM32WBA55HG, **ISM330DHCX**, MCP1640, LDL112, IIS2MDC,
DSC1001, TPS7A02, DRV5032, IRLML6402, e la **TN0018** di ST sul montaggio dei MEMS.
Ci sono tutti.

## La scheda
Risveglio dello stack smash, fra `power_board` (sopra) e `fin_ble_board` (sotto).
Tonda **Ø34 mm**, **14 layer**, stackup **2.225 mm**.
114 componenti (30 top, 84 bottom), **92 net, 439 pin**.
Non esiste `.kicad_sch`: le net stanno sui pad come `(net "NOME")`.

## FATTO

### Regole NCAB — set completo
`wakeup_board.kicad_dru`, con le regole specifiche **dopo** quelle generali
(l'ordine inverso aveva nascosto 389 violazioni su aft_end_board):
clearance 100 µm · pista 100 µm · foro-foro 250 µm · rame-bordo 250 µm ·
via-pista 150 µm · via-via 250 µm · punta **250 µm** · pad via 450 µm.

**Aspect ratio**: 2.205 mm da forare. Con punta 0.20 sarebbe 11.0:1, fuori standard —
lo stesso problema aperto su aft_end_board. Qui, essendo prima del routing, il default e
**via 0.50 / punta 0.25 → 8.8:1**.

### 8 piani creati, riempiti e verificati nel Gestore zone

| Layer | Net | | Layer | Net |
|---|---|---|---|---|
| In1.Cu | FLEX_GND | | In7.Cu | FLEX_GND |
| In2.Cu | 3V3_AON | | In10.Cu | FLEX_GND |
| In4.Cu | FLEX_GND | | In11.Cu | 3V3 |
| In6.Cu | 3V3 | | In12.Cu | FLEX_GND |

Parametri (letti dal file, coincidono col dialogo di KiCad):
- geometria: disco **R16.5** a 48 vertici → rame-bordo **0.50 mm** (minimo NCAB 0.25)
- clearance **0.15**, larghezza minima **0.15**
- collegamento piazzole: **raccordi termici**, apertura 0.5, larghezza 0.5
- `island_removal_mode 0` = **Rimuovi isole: Sempre**
- riempimento: 1 `filled_polygon` per zona, 234 vertici (i due fori sono le isole di potting)

Layer di segnale liberi: **F.Cu, In3, In5, In8, B.Cu**.
In9 e riservato al **power path** (zone separate BAT_RAW / BAT_PROT / REG_IN_MAIN / BOOST_OUT),
ancora da fare.

### Perche il DRC segnala 8 `isolated_copper`
E corretto: un piano interno non tocca i pad di F.Cu/B.Cu finche non ci sono via di cucitura.
Spariranno col routing. **Attenzione**: con *Rimuovi isole = Sempre*, un ri-riempimento dalla GUI
prima della cucitura potrebbe svuotare i piani. Il riempimento fatto da `kicad-cli --refill-zones`
li ha mantenuti (234 vertici), ma tienilo d'occhio.

## DA FARE — in quest'ordine

1. ~~Pin 1 di `U_IMU3`~~ — **RISOLTO, non era un errore**: il pin 1 dell'ISM330DHCX e `SDO/SA0`,
   l'indirizzo I2C. IMU2 e IMU3 condividono I2C3 e devono avere indirizzi diversi (0x6A / 0x6B):
   il collegamento e voluto e corretto.
2. ~~Footprint `LSM6DS3USTR (LGA-14)`~~ — **CORRETTO**: swap w/h sugli 8 pad verticali,
   gap 0.025 → **0.250 mm**, come da datasheet. Fatti sia il `.kicad_mod` sia le 3 istanze.
   **DRC clearance 20 → 2.**
2-bis. ~~`U_MAG_WAKE` (DRV5032FCQDBZR)~~ — **CORRETTO**: footprint sostituito con
   `SOT95P237X112-3N` (lo stesso di QMAIN) e scambiate le net fra pad 2 e 3, perche la
   numerazione del vecchio footprint era non standard. Pinout ora conforme alla Table 5-1:
   1 VCC / 2 OUT / 3 GND. **DRC clearance: 20 → 2 → 0.**
3. **SWD del BLE**: `WBA_SWCLK` (F1) e `WBA_SWDIO` (E8) hanno **un solo nodo**. Il micro non e
   programmabile ne debuggabile. Da portare a un connettore o a due test point.
4. **Catena RF**: `RF1` → pi (0.5 pF + 2.7 nH + 0.5 pF) → `WBA_RF_M`, che **non prosegue**.
   `YAGI_RF_A/B` e `YAGI_WILK_A/B` sono test point isolati. Manca il collegamento all'antenna.
5. **`U_PWR` enable flottante**: pin 3 (EN) e pin 5 non connessi sull'LDL112.
6. **`C_WBA_VDD11` = 2.2 µF**, il datasheet chiede **4.7 µF totali** sull'uscita SMPS.
7. **`VDDHPA`**: ST lo descrive come pin per condensatore esterno da 470 nF, non come ingresso
   di alimentazione; sulla board risulta legato a `3V3_AON` con un 100 nF. Da verificare sulla
   tabella dei ball del WLCSP41 (i pinout nel PDF sono figure, non testo estraibile).
8. **In9 — power path** a zone separate.
9. **Cucitura di massa**: via che legano i pad GND di F.Cu/B.Cu ai cinque piani.
10. **Routing**, poi DRC finale e pacchetto fab.

I punti 1, 2 e 2-bis sono chiusi. Restano decisioni di progetto (3, 4, 5) prima del routing.

## Regole operative su queste board
- **KiCad chiuso** quando si edita da script: alla prima Salva la GUI sovrascrive tutto
  (successo davvero il 10/09 alle 14:07).
- `add_zone` di Konnect scrive `(net 0) (net_name "X")`: su queste board va riscritto in
  `(net "X")`, la forma usata dai pad. Altrimenti la zona nasce scollegata.
- `kicad-cli pcb drc` vuole **`--refill-zones`** (e `--save-board` per persistere), come i gerber
  vogliono `--check-zones`.
- Non giudicare un piano dal conteggio dei non connessi: senza via e sempre isolato.
