# wakeup_board — schema dei piani di alimentazione

## Vincoli letti dal datasheet PRIMA di assegnare i piani
Da `datasheets\stm32wba55hg.pdf` (DS14127 Rev 10, pag. 28-29):

- `VDDA`, `VDDSMPS`, `VDDRF` **devono stare sulla stessa alimentazione di VDD**.
  Sulla board tutti gli 8 ball di alimentazione sono su `3V3_AON` → **rispettato**.
- `VDDANA` e `VDDRFPA` devono essere **≤ VDDRF**. Stesso rail → uguali, **ok**.
- SMPS: serve l'induttore fra `VLXSMPS` e `VDD11`. Presente (`L_WBA_SMPS` 2.2 µH) → **ok**.
- `VDD11` vuole un condensatore esterno **totale di 4.7 µF tipici**.
- `VDDHPA` e un pin **per un condensatore esterno, 470 nF tipici**, non un ingresso di alimentazione.

## Schema proposto — 14 layer

| Layer | Assegnazione | Perche |
|---|---|---|
| F.Cu | segnale + attivi | 30 componenti, la rete pi RF, il BGA |
| **In1** | **FLEX_GND solido** | riferimento RF a 0.15 mm sotto F.Cu: il ritorno del pi e dell'antenna deve vedere un piano continuo, senza tagli |
| **In2** | **3V3_AON** | coppia con In1 sul core da **0.05 mm** → ~0.64 nF di capacita di piano proprio sul rail che alimenta VDD/VDDRF/VDDSMPS/VDDA del BLE |
| In3 | segnale | |
| **In4** | **FLEX_GND** | |
| In5 | segnale | |
| **In6** | **3V3** | rail digitale dei sensori, 47 nodi |
| **In7** | **FLEX_GND** | |
| In8 | segnale | |
| **In9** | **power path**: zone separate `BAT_RAW`, `BAT_PROT`, `REG_IN_MAIN`, `BOOST_OUT` | correnti del boost tenute lontane dal piano RF |
| **In10** | **FLEX_GND** | |
| **In11** | **3V3** (secondo piano) | |
| **In12** | **FLEX_GND** | riferimento per B.Cu, coppia con In11 sul core da 0.05 mm |
| B.Cu | segnale + passivi | 84 componenti |

**5 piani di massa** (In1, In4, In7, In10, In12), 2 di 3V3, 1 di 3V3_AON, 1 per il power path,
5 facce di segnale (F.Cu, In3, In5, In8, B.Cu).

Capacita di piano delle due coppie sui core sottili: disco R16.5 = 8.55 cm²,
`C = ε0 · 4.2 · A / 0.05 mm` ≈ **0.64 nF a coppia**, ~1.3 nF in totale.

Geometria zone: disco **R16.5** (rame-bordo 0.50 mm, il minimo NCAB e 0.25),
clearance 0.15, larghezza minima 0.15.

## FATTO — 8 piani creati e riempiti (10/09/2026)

| Layer | Net | filled_polygon | vertici |
|---|---|---|---|
| In1.Cu | FLEX_GND | 1 | 234 |
| In2.Cu | 3V3_AON | 1 | 234 |
| In4.Cu | FLEX_GND | 1 | 234 |
| In6.Cu | 3V3 | 1 | 234 |
| In7.Cu | FLEX_GND | 1 | 234 |
| In10.Cu | FLEX_GND | 1 | 234 |
| In11.Cu | 3V3 | 1 | 234 |
| In12.Cu | FLEX_GND | 1 | 234 |

Il DRC le riconosce tutte e otto con la net giusta (`Zona [FLEX_GND] su In1.Cu`, ecc.).

### La ricetta (vale per tutte le board smash)
Le board generate da smash **non hanno tabella net**: i pad portano `(net "NOME")`, solo il nome.
KiCad costruisce comunque le net internamente — il ratsnest e 439 pin − 92 net = 347, esatto.

`add_zone` di Konnect pero scrive la zona nella forma KiCad standard `(net 0) (net_name "X")`,
e senza tabella lo 0 vuol dire "nessuna net": la zona nasce scollegata.

**Fix**: dopo `add_zone`, riscrivere `(net 0) (net_name "X")` → `(net "X")`.
E' esattamente la forma usata dai pad di queste board e dalle zone di `aft_end_board`.

Altra trappola: **`kicad-cli pcb drc` non riempie le zone** se non gli passi `--refill-zones`
(come i gerber vogliono `--check-zones`). Senza, le zone risultano vuote e sembrano non funzionare.

### Perche il DRC segnala 8 `isolated_copper`
E corretto e atteso: un piano su layer interno non puo toccare pad che stanno su F.Cu e B.Cu
**finche non ci sono via di cucitura**. Spariranno col routing. Su `aft_end_board` i piani si
chiudono perche li ci sono gia 156 via.

### Stato DRC dopo i piani
- 347 non connessi — invariato, la scheda non e routata
- 20 clearance — sono i pad interni dei footprint IMU difettosi (vedi STATO_wakeup_board.md)
- 8 isolated_copper — i piani, attesi
- 73 lib_footprint_mismatch + 21 di serigrafia

## Due riscontri sul progetto, dal datasheet

**`C_WBA_VDD11` e 2.2 µF, il datasheet ne chiede 4.7 µF totali** sull'uscita SMPS. Sottodimensionato.

**`VDDHPA`**: il datasheet lo descrive come pin per un condensatore esterno da 470 nF, non come
ingresso di alimentazione. Sulla board il ball corrispondente risulta legato a `3V3_AON` con un
`C_WBA_VDDHPA` da 100 nF. Da verificare sulla tabella dei ball del WLCSP41: se VDDHPA e davvero
un'uscita di regolatore, collegarlo al rail e sbagliato. Non sono riuscito a estrarre la mappa
ball→funzione dal PDF (i pinout sono figure), va letta a occhio sulla tabella dei pin.
