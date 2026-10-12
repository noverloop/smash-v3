# wakeup_board — punto di partenza (10/09/2026)

File: `G:\fin_ble and wakeup\wakeup_board\wakeup_board.kicad_pcb`
Schematico ricostruito: `docs\wakeup_board_schematico.svg`

## Cos'e
Scheda di risveglio dello stack smash, fra `power_board` (sopra) e `fin_ble_board` (sotto).
Tonda Ø34 mm, **14 layer**, stackup 2.225 mm. 114 componenti, 92 net, 439 pin.

## Stato: PLACEMENT SOLO
- **0 tracce, 0 via, 0 zone.** La scheda non e routata per niente.
- **Nessun `.kicad_sch`**: le net sono assegnate direttamente ai pad, in forma `(net "NOME")`
  senza tabella net. Lo schematico e stato ricostruito da li.
- DRC di partenza: **347 elementi non connessi** (atteso) + 20 violazioni di clearance reali.

## Architettura

| Blocco | Componenti |
|---|---|
| Risveglio | reed `RR123-1H02-612` + hall `DRV5032FCQDBZR` + piazzola JUMP_PAD, OR con due `BAT64-06` |
| Potenza | `IRLML6402` load switch → boost `MCP1640` (3.87 V) → LDO `LDL112PV33R` → **3V3** |
| Rail sempre-acceso | `TPS7A0233` (Iq 25 nA) + latch `IRLML6402`, il micro si autoritiene via E4 |
| Timer | secondo `TPS7A0233` con IN+EN su BAT_RAW → TMR_VDD per il reed |
| MCU | `STM32WBA55HGF6TR` BGA41, SMPS interno con 2.2 µH, HSE MEMS 32 MHz, rete pi RF |
| Sensori | 3× IMU `ISM330DHCX` (I2C2 + I2C3) + magnetometro `IIS2MDC` |
| Stack | 2 connettori LGA da 65 e 69 land: portano 62 delle 92 net |

Boost: `Vout = 1.21 × (1 + 220k/100k) = 3.87 V`, che alimenta un LDO 3.3 V → 570 mV di margine.

## PROBLEMI TROVATI

### 1. SWD del BLE non collegato
`WBA_SWCLK` (pin F1) e `WBA_SWDIO` (pin E8) hanno **un solo nodo ciascuna**.
Non arrivano né a un connettore né a un test point: **il micro non e programmabile né debuggabile**.

### 2. La catena RF finisce nel vuoto
`U_WBA.C2` (RF1) → `C_WBA_PI1` 0.5 pF + `L_WBA_PI` 2.7 nH + `C_WBA_PI2` 0.5 pF → `WBA_RF_M`,
che **non prosegue**. Le net d'antenna `YAGI_RF_A`, `YAGI_RF_B` sono test point isolati,
e `YAGI_WILK_A/B` hanno solo il resistore di isolamento `R_WILK_ISO` 100 Ω fra due test point.
Manca il collegamento fra rete di adattamento e antenna.

### 3. ~~U_IMU3 ha il pin 1 su 3V3~~ — RISOLTO, NON era un errore
Il datasheet ISM330DHCX (DS13012 Rev 7, Tabella 1) dice che **il pin 1 e `SDO/SA0`**, cioe il bit
meno significativo dell'indirizzo I2C — non un pin di alimentazione. Quindi:

| | bus | SA0 | indirizzo |
|---|---|---|---|
| U_IMU1 | I2C2 | GND = 0 | 0x6A |
| U_IMU2 | I2C3 | GND = 0 | 0x6A |
| U_IMU3 | I2C3 | 3V3 = 1 | **0x6B** |

`U_IMU2` e `U_IMU3` **condividono I2C3**, quindi devono avere indirizzi diversi: e esattamente
per questo che il pin 1 di IMU3 sta alto. Il collegamento e **corretto e voluto**.
Avevo dedotto male dando per scontato che il pin 1 fosse alimentazione.

Verificato col datasheet anche il resto: pin 5 `Vdd_IO`, 8 `Vdd`, 12 `CS` su 3V3 (CS alto = I2C
abilitato, giusto), pin 6 e 7 GND, pin 10 `OCS_Aux` e 11 `SDO_Aux` non connessi — il datasheet
dice proprio "leave unconnected". Tutto in ordine.

### 4. LDO principale con enable flottante
`U_PWR` (LDL112PV33R): pin 3 (EN) e pin 5 **non connessi**. Se EN e davvero flottante l'LDO
non parte in modo deterministico. Da verificare sul datasheet e legare a IN o a un controllo.

### 5. Footprint IMU difettoso — CORRETTO (10/09/2026)
`SmashWakeupBoard:LSM6DS3USTR (LGA-14)` aveva gli **8 pad delle colonne verticali** (1-4 e 8-11)
di 0.25 × 0.475 con il lato lungo **lungo il passo** di 0.5 → gap **0.025 mm**, 18 violazioni.
I 6 pad orizzontali (5-7, 12-14) erano gia corretti.

Il datasheet (pag. 146, LGA-14L) da le land **0.475 × 0.25**: il lato lungo va perpendicolare
al passo. Fatto lo swap w/h sugli 8 verticali → **gap 0.250 mm**, esattamente il valore atteso.
Corretti sia il `.kicad_mod` di libreria sia le 3 istanze nel `.kicad_pcb`.
**DRC clearance: 20 → 2.**

### 5-bis. `U_MAG_WAKE` (DRV5032FCQDBZR) — CORRETTO (10/09/2026)

Il footprint `SmashWakeupBoard:DRV5032FCQDBZR` era sbagliato su cinque punti:
pad **quadrati 1.286 × 1.286**, passo **1.27 mm** (= 50 mil, griglia generica) invece di 0.95,
pad **1 e 3 accoppiati** col 2 solitario (in un SOT-23 stanno insieme 1 e 2), origine sul pad 1
invece che al centro, courtyard 6.00 × 4.586 per un corpo da 2.9 × 1.3.
Fra pad 1 e 2 restavano **0.014 mm** di rame.

**Attenzione al tranello**: nonostante la numerazione sbagliata, i collegamenti *fisici* erano
corretti — VCC e OUT sui due pad accoppiati, GND sul solitario. Cambiare solo il footprint
avrebbe messo la massa sull'uscita open-drain. Servivano due mosse insieme.

Fatto:
1. footprint → **`SmashWakeupBoard:SOT95P237X112-3N`** (lo stesso di QMAIN e Q_AON_EN; il
   datasheet TI intitola il package "SOT-23 - 1.12 mm max height", che e esattamente 95P237X112)
2. scambiate le net fra pad 2 e pad 3

Risultato, confrontato con la Table 5-1 del datasheet DRV5032 (versione FC, SOT-23):

| pad | funzione TI | posizione | net |
|---|---|---|---|
| 1 | VCC | accoppiato | `3V3_AON` |
| 2 | OUT | accoppiato | `MAG_WAKE_N` |
| 3 | GND | solitario | `FLEX_GND` |

Il rame sotto il componente e identico a prima; cambiano numerazione e land pattern.
**DRC clearance: 20 → 2 → 0.**

### 6. Da chiarire
Pin non connessi da verificare sul datasheet: `U_MAG` 2/11/12, `U_IMU*` 10/11, `U_WBA` B7/D7/D11/F7.
Il gate di `QMAIN` e tirato su `BAT_RAW` mentre il source e su `BAT_PROT`: net diverse.

## Regole NCAB — applicate
`wakeup_board.kicad_dru` contiene il set **completo**, con le regole specifiche DOPO le generali
(l'ordine sbagliato aveva nascosto 389 violazioni su aft_end_board):

| Regola | Valore |
|---|---|
| clearance rame-rame | 100 µm |
| larghezza pista | 100 µm |
| foro ↔ foro | 250 µm |
| rame ↔ bordo | 250 µm |
| via ↔ pista | 150 µm |
| via ↔ via | 250 µm |
| punta minima | **250 µm** |
| pad via | 450 µm |

**Aspect ratio**: 2.205 mm da forare. Con punta 0.20 sarebbe 11.0:1, fuori standard — lo stesso
problema aperto su aft_end_board. Qui siamo prima del routing, quindi il default di progetto e
**via 0.50 / punta 0.25 → 8.8:1**, dentro la galvanica standard.

## Datasheet
In `datasheets\`. Presenti: **STM32WBA55HG** (salvato dal browser), TPS7A02, DRV5032, IRLML6402.
**Da scaricare a mano** (st.com e Microchip bloccano curl, dal browser funzionano):
- https://www.st.com/resource/en/datasheet/ism330dhcx.pdf
- https://www.st.com/resource/en/datasheet/iis2mdc.pdf
- https://www.st.com/resource/en/datasheet/ldl112.pdf
- MCP1640 e DSC1001 dal sito Microchip

Servono per: layout RF e decoupling dell'STM32WBA, pinout ISM330DHCX (problema 3),
enable dell'LDL112 (problema 4), layout del boost MCP1640.
