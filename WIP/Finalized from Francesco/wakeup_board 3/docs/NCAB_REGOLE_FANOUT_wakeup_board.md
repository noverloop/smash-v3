# wakeup_board – Regole NCAB riviste e fanout HDI di U_WBA

*11-09-2026 · KiCad 10.0.3 · file `wakeup_board.kicad_pcb`*
*Backup degli originali: `backup_pre_NCAB_fanout_20260911_173525\`*

---

## 1. Revisione del `.kicad_dru` precedente

Il `.dru` è stato verificato su una scheda di test a 14 layer con `kicad-cli pcb drc`.

**Cosa era corretto**

- I valori coincidono con `hdi_fab_rules.md`: 100/100 µm, via↔via 250 µm, via↔pista 150 µm.
- L'ordine è giusto: prima le regole generali, poi le specifiche.
- `severity` funziona.

**Cosa andava corretto**

| # | Problema | Effetto |
|---|---|---|
| 1 | `A.Via_Type == 'Blind/buried'`: in KiCad 10 i tipi sono `Blind` e `Buried`, separati | punta minima e pad 0,45 **non venivano mai controllati** sui via interrati e ciechi |
| 2 | nessuna regola sull'anello del via | un via 0,45/0,25 (anello 0,10) passava; il foglio NCAB (0,2/0,45) implica 0,125 |
| 3 | nessuna regola per i microvia; rame-foro a 0,25 in Board Setup | i microvia servono (vedi §3), ma nel pad del WLCSP starebbero a 0,24 mm dalla sfera vicina |
| 4 | nessuna deroga locale per il BGA | NCAB ammette 80/80 µm, il fabbricante 70/70 µm |
| 5 | punta minima 0,25 calcolata su uno stackup da 2,225 mm | NCAB chiede 1,6–2,0 mm; lo spessore generale del file era già 1,6 |
| 6 | "rame-bordo 250 µm" | il valore non compare in nessuna delle due fonti |

---

## 2. Nuovo `wakeup_board.kicad_dru`

Fonti: foglio NCAB (**DOC**) e `hdi_fab_rules.md` (**FAB**). I valori **ASS** sono assunti e da confermare con NCAB.

| Regola | Valore | Fonte |
|---|---|---|
| Pista minima | 0,10 mm | DOC, FAB |
| Deroga BGA (Rule Area `BGA*`): pista e isolamento | 0,08 mm | DOC |
| Rame dal bordo | 0,30 mm | ASS |
| Punta meccanica minima | 0,20 mm (stackup NCAB circa 1,6 mm) | DOC |
| Via meccanici: pad / anello | 0,45 / 0,125 mm | DOC |
| Microvia: foro / pad / anello | 0,10 (max 0,15) / 0,25 / 0,075 mm | DOC |
| Rame-foro | 0,20 meccanici · 0,10 microvia verso piste e zone | ASS |
| Foro-foro | 0,25 meccanici · 0,15 microvia | FAB / ASS |
| Via↔pista 0,15 e via↔via 0,25 | solo via meccanici | FAB |
| Span dei via | microvia 1-2, 2-3, 12-13, 13-14 · meccanici 1-14, 2-13, 3-12 | DOC |

- **Perché via↔pista e via↔via valgono solo per i meccanici:** sotto il WLCSP i microvia nel pad distano per costruzione 0,15 mm bordo-bordo.
- **Microvia non impilati (FAB):** KiCad non lo verifica. Il fanout usa solo microvia 1-2, quindi non ce ne sono di impilati.

**Board Setup** (minimi assoluti):

- clearance 0,08 · pista 0,08 · anello 0,075 · via 0,25;
- rame-foro 0,10 · rame-bordo 0,30;
- foro 0,20 · foro-foro 0,15 · µVia 0,25/0,10.

**Net class**

| Classe | Net | Clearance | Pista | Via | µVia |
|---|---|---|---|---|---|
| Default | tutte le altre | 0,10 | 0,10 | 0,45 / 0,20 | 0,25 / 0,10 |
| POWER | BAT_RAW, BAT_PROT, REG_IN_MAIN, BOOST_OUT, BOOST_SW, COMP_5V, COMP_5V_RAW | 0,10 | 0,25 | 0,45 / 0,20 | 0,25 / 0,10 |

**Tipo dei layer:** In1, In2, In4, In6, In7, In10, In11 e In12 (quelli con piano) sono ora di tipo **power**, così Freerouting non ci sbroglia piste. In9 resta di segnale, perché il power path a zone non è stato fatto.

---

## 3. Fanout HDI di U_WBA (STM32WBA55, WLCSP41 passo 0,35 mm)

**Il problema.** Le sfere hanno pad Ø0,221 mm con 0,179 mm di spazio tra l'una e l'altra. Tra due sfere non passa nessuna pista: servirebbero 0,30 mm con 100/100, e 0,24 mm anche con la deroga 80/80. Delle 41 sfere, 20 non hanno un'uscita dritta a 0/45/90° su F.Cu. Di queste 15 sono collegate:

- 3 FLEX_GND: B9, D3, D5;
- 12 segnali o alimentazioni: B11 VDD11, C6 3V3_AON, C8 BOOT0, C10 HCI_IRQ, D9 IR_TX, E4 AON_HOLD, E6 IR_WAKE, E10 UART_RX, F3 I2C2_SCL, F5 WBA_WAKE, F9 HCI_MISO, F11 UART_TX.

La sfera E8 (WBA_SWDIO) ha un solo nodo e per ora non è sbrogliata.

**La soluzione** (script `scripts_NCAB\fanout_uwba.py`):

1. **Microvia laser 0,10/0,25** nel pad delle 15 sfere, da F.Cu a In1.Cu, riempiti di rame e capped. Le 3 GND scendono dirette sul piano In1.
2. **Uscite su In1.Cu** con piste da 0,10 mm, su percorsi disgiunti del reticolo esagonale delle sfere (flusso massimo con capacità 1 per nodo). Le uscite passano solo dove su In1 non c'è rame; per costruzione restano ad almeno 0,17 mm dai microvia e 0,25 mm dalle altre piste.
3. **12 via di fanout** 0,45/0,20 fuori dal campo sfere:
   - almeno 0,80 mm l'uno dall'altro;
   - almeno 0,75 mm dalle sfere;
   - almeno 0,33 mm dai pad di F.Cu e B.Cu.
4. **Corridoi di massa:** due piste FLEX_GND su In1 (da B9 e da D5-D3) collegano le microvia GND al piano esterno.
5. **Zona di rispetto RF:** nessuna pista su In1 entro 0,55 mm dal tratto iniziale della rotta WBA_RF (dalla sfera C2 verso C_WBA_PI1).
6. **Tutto bloccato (locked)**, così Freerouting non lo tocca.

**Risultato:** 15 microvia, 51 segmenti su In1, 12 via di fanout. DRC con **0 errori**; restano 334 connessioni da sbrogliare. Immagine: `fanout_U_WBA_In1.png`.

**Il compromesso.** Sotto il chip il piano GND di In1 è molto bucato, e due uscite (BOOT0 e 3V3_AON) sono lunghe 17–21 passi.

---

## 4. Stackup NCAB da inserire a mano

L'API Python di KiCad 10 non espone lo stackup, quindi va inserito in **Board Setup → Physical Stackup**. Valori dall'immagine dell'Appendix A NCAB:

| Strato | Tipo | Spessore (mm) | Dk |
|---|---|---|---|
| F.Mask | solder mask | 0,01016 | 3,5 |
| F.Cu | rame | 0,035 | |
| dielettrico 1 | prepreg PP-001 | 0,0508 | 3,9 |
| In1.Cu | rame | 0,035 | |
| dielettrico 2 | prepreg PP-006 | 0,07112 | 4,1 |
| In2.Cu | rame | 0,035 | |
| dielettrico 3 | core | 0,07112 | 4,1 |
| In3.Cu … In5.Cu | rame | 0,035 | |
| dielettrici 4, 5, 6 | prepreg PP-006 | 0,07112 | 4,1 |
| In6.Cu | rame | 0,03556 | |
| dielettrico 7 | core Core-025 | 0,2032 | 4,6 |
| In7.Cu | rame | 0,03556 | |
| dielettrici 8, 9, 10 | prepreg PP-006 | 0,07112 | 4,1 |
| In8.Cu … In10.Cu | rame | 0,035 | |
| dielettrico 11 | core | 0,07112 | 4,1 |
| In11.Cu | rame | 0,035 | |
| dielettrico 12 | prepreg PP-006 | 0,07112 | 4,1 |
| In12.Cu | rame | 0,035 | |
| dielettrico 13 | prepreg PP-001 | 0,0508 | 3,9 |
| B.Cu | rame | 0,035 | |
| B.Mask | solder mask | 0,01016 | 3,5 |

Tra due layer di rame consecutivi c'è un solo dielettrico (13 in tutto): la tabella raggruppa i layer e i dielettrici ripetuti.

- **Totale:** circa 1,53 mm. Il foglio chiede 1,6–2,0 mm, quindi NCAB dovrà ritoccarlo.
- **Rame:** il foglio indica 18 µm, l'immagine 35 µm. Da chiarire.
- **Obbligatorio per i microvia:** nello stackup attuale il dielettrico F.Cu→In1 è 0,15 mm, cioè aspect ratio 1,5:1 per un foro da 0,10. Il fabbricante vuole al massimo 0,8:1. Con lo stackup NCAB (0,0508 mm) si arriva a 0,5:1.

---

## 5. Routing con Freerouting

1. Aprire wakeup_board in KiCad e lanciare il plugin. I layer power vengono trattati come piani; fanout e microvia sono bloccati.
2. Freerouting conosce solo il clearance della net class (0,10). Le regole FAB via↔via 0,25 e via↔pista 0,15 vanno verificate col DRC dopo il routing.
   - Portare il clearance di routing a 0,15 non è possibile: il piazzamento su B.Cu ha già 133 coppie di pad sotto 0,15 mm.
3. Al rientro premere **B**, salvare e lanciare il DRC.

---

## 6. Punti aperti

**Piazzamento: il routing non li risolve**

- [ ] **WBA_RF:** la rete π (C_WBA_PI1) è a circa 10 mm dalla sfera C2. Va avvicinata al pin e l'RF va sbrogliato a mano (50 Ω, niente via), non da Freerouting.
- [ ] **SMPS:** L_WBA_SMPS è a circa 5 mm da U_WBA. ST chiede l'induttore attaccato ai pin VLXSMPS/VDD11.
- [ ] **HSE:** Y_WBA_HSE è a circa 16 mm da U_WBA.

**Progetto** (da `STATO_wakeup_board.md`)

- [ ] SWD non collegato (WBA_SWDIO E8, WBA_SWCLK F1).
- [ ] Catena RF che non arriva all'antenna.
- [ ] EN dell'LDL112 flottante.
- [ ] C_WBA_VDD11 da 2,2 µF, il datasheet ne chiede 4,7.

**Verifiche**

- [ ] Stackup NCAB inserito in KiCad (§4).
- [ ] Valori ASS confermati da NCAB.
- [ ] Dopo il routing: DRC, regole FAB sui via, colata GND esterna e cucitura.
- [ ] **aft_end_board** ha lo stesso stackup da 2,225 mm nel file e punte da 0,20 mm. Il job file dichiara 1,6 mm: allineare l'ordine allo stackup NCAB.

---

## 7. Piazzamento del boost e autorouting (12-09-2026)

### 7.1 Piazzamento mirato
Backup: `backup_pre_placement_20260912_094341\`. Spostati solo i componenti dell'anello di
commutazione del boost, con verifica di courtyard, pad, via e piste a ogni posizione:

| Componente | Distanza dal pin di destinazione prima | dopo |
|---|---|---|
| L_PWR | 19,2 mm | 3,5 mm |
| CBOOST_IN1_1 | 20,4 | 2,0 |
| CBOOST_IN1_2 | 13,5 | 3,2 |
| CBOOST_IN1_3 | 18,0 | 4,0 |
| CBOOST_IN1_4 | 13,3 | 5,1 |
| CBOOST_IN1_5 | 9,6 | 5,8 |
| CBOOST_IN2 | 21,2 | 5,8 |
| CBOOST_OUT2 | 11,8 | 5,7 |

Non spostati per mancanza di spazio: rete pi RF (al massimo 5,5 mm dalla sfera C2, e sposterebbe
il corridoio RF tenuto libero nel fanout), induttore SMPS e oscillatore HSE. Servono un
ripiazzamento complessivo e i vincoli meccanici.

### 7.2 Autorouting con Freerouting 2.3.0
Backup prima del routing: `backup_pre_routing_20260912_122228\`.

Freerouting riceve solo cio che sta nel DSN: larghezze, clearance e via delle net class. Le regole
NCAB sono state passate cosi:

- elenco via ridotto al solo passante 0,45/0,20 (niente microvia nel routing automatico);
- `--router.copper_to_edge_clearance_um=300` per il rame dal bordo;
- `--router.automatic_neckdown=false`;
- fanout dei pin SMD limitato a 3 passate.

**Cose imparate, con prove:**

- `--router.hole_clearance_um=200` (rame-foro) va evitato: fa vedere a Freerouting 169 violazioni
  inesistenti e impedisce i via attraverso i piani. Il DRC di KiCad controlla comunque la regola.
- Le posizioni dei pin nel DSN sono corrette: verificate su tutti i 456 pad, e un test con un DSN
  minimo conferma che Freerouting specchia sulla X come esporta KiCad. Una correzione basata
  sull'ipotesi contraria e stata provata e **scartata** (peggiorava: 144 cortocircuiti).
- Freerouting attraversa i pad di alcuni componenti (13 su 114) nonostante il clearance:
  i cortocircuiti vanno tolti dopo l'import.
- Il parametro `clearance_violation_penalty` non e impostabile da riga di comando (tipo errato);
  nel file di configurazione non cambia il risultato.

**Risultato** (giro migliore: 5 passate, 39 minuti): 108 collegamenti aperti su 344.

### 7.3 Pulizia dopo l'import
Script in `scripts_NCAB\`: `cleanup_routing.py`, `cleanup2.py`, `clean_dangling.py`.

| Voce | Dopo autorouting | Dopo pulizia |
|---|---|---|
| Cortocircuiti | 48 | 0 |
| Piste sotto 0,10 mm | 38 | 0 |
| Ponti di solder mask | 53 | 0 |
| Rame-foro < 0,20 | 5 | 0 |
| Via-pista < 0,15 / via-via < 0,25 (regole fabbricante) | 301 | 281 |
| Collegamenti aperti | 126 | 140 |

Stato della scheda: 1413 piste circa, 175 via, nessun errore di rame salvo le due regole del
fabbricante sui via, che Freerouting non puo ricevere e che vanno sistemate durante il lavoro a mano.

Elenco dei collegamenti da chiudere: `docs\DA_COMPLETARE_wakeup_board.md` (140, di cui 94 su net
con piano: basta un via verso il piano). Immagini dei layer in `routing_prova
outing_pulito.png`;
in `routing_prova\wakeup_routed.kicad_pcb` c'e una copia apribile in KiCad.

---

## 8. Chiusura collegamenti via script e riduzione taglie (12-09-2026)

### 8.1 Via verso i piani
Script `scripts_NCAB\gnd_vias.py`, `plane_vias.py`, `maze_vias.py`.
Per ogni pad scollegato di una net con piano si cerca il punto libero piu vicino, si mette un
via passante 0.45/0.20 e si collega al pad con una pista da 0.10 mm. Vincoli applicati nella
ricerca: 0.10 dal rame di altre net, 0.15 via-pista, 0.25 via-via, 0.20 rame-foro, 0.45
foro-foro, 0.30 dal bordo. Per le net di In9 il via deve cadere nella regione della propria net.

- via diretti e percorsi a gomito: **42 collegamenti chiusi**
- router a griglia 0.05 mm, tratti a 45/90 gradi, raggio 6 mm: **13**
- stesso router a 10 mm: nessun guadagno netto (i percorsi trovati violavano le distanze)

### 8.2 Riduzione di taglia di alcuni passivi
Script `scripts_NCAB\shrink_parts.py`. Backup: `backup_pre_shrink_20260912_143149\`.

| Componenti | Da | A | Nota |
|---|---|---|---|
| C_MAG2, C_AON_IN, C_AON_OUT, C_TMR_LDO (1 uF X7R) | 0805 | 0603 | disponibile anche in MIL-PRF-32535 |
| C_MAG_C1 (220 nF X7R) | 0603 | 0402 | da confermare in mil-spec |
| C_WBA_PI1, C_WBA_PI2 (0.5 pF RF) | 0603 | 0402 | per l'RF il 0402 e preferibile |
| 11 test point | Ø1.5 mm | Ø1.0 mm | verificare le sonde |

I 2.2 uF X7R restano 0603: in 0402 servirebbe X5R commerciale a bassa tensione.

Dopo la riduzione le piste che finivano sui pad grandi sono state rimosse e il router rilanciato:
**30 collegamenti chiusi** nei corridoi liberati.

**Da rifare a mano** (tolti con la riduzione): TMR_VDD su C_TMR_LDO, MAG_C1_TERM su C_MAG_C1,
WBA_RF e WBA_RF_M sulla rete pi (che va comunque sbrogliata a mano).

### 8.3 Stato finale
| Voce | Valore |
|---|---|
| Piste / via / rame | 1607 / 249 / 1869 mm |
| Collegamenti aperti | **80** (erano 344 all'inizio) |
| Errori DRC | **265**, tutti e soli via-pista < 0.15 e via-via < 0.25 (regole del fabbricante) |
| Cortocircuiti, piste sotto 0.10, ponti di maschera, rame-foro | 0 |

Elenco aggiornato dei collegamenti da chiudere: `docs\DA_COMPLETARE_wakeup_board.md`.

