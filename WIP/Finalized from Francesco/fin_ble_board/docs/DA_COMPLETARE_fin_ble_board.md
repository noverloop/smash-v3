# fin_ble_board – collegamenti da chiudere a mano

*Stato al 24/09/2026 dopo Freerouting 2.4.1 + via ai piani via script: **26 collegamenti aperti, 0 cortocircuiti, 3 errori di distanza.***

In KiCad: **Ispezione → Controllo regole di progettazione → Esegui DRC → scheda "Elementi non connessi"**: un doppio clic porta sul punto. 
Strumento pista **X**, via durante lo sbroglio **V**, cambio strato **PgSu/PgGiù**. Regole NCAB: pista 0,10 mm (POWER 0,25, MOTOR 0,30), isolamento 0,10, via 0,45/0,20, via-pista 0,15, via-via 0,25.

## 1. Errori di distanza (da sistemare per primi)

| Dove | Problema | Cosa fare |
|---|---|---|
| (−6,96; 11,26) | pista FIN4_AEN su In3 a meno di 0,15 mm dalla via 3V3 del fanout | spostare il tratto di pista di 0,1 mm |
| (−0,97; 8,50) | via FIN3_APH a meno di 0,25 mm dalla via 3V3 del fanout | spostare la via FIN3_APH (trascinare con **D**) |
| (−1,13; 7,83) | via SYS_SPI_CS_FIN a meno di 0,25 mm dalla via 3V3 del fanout | spostare la via SYS_SPI_CS_FIN |

Le via 3V3 del fanout e tutto il fanout del BGA sono **bloccati**: spostare le via di Freerouting, non quelle.

## 2. Alimentazione e massa (11)

| Net | Da | A | Distanza |
|---|---|---|---|
| 3V3 | Pista [3V3] su B.Cu, lung. 1.2243 mm (-9.55; 7.28) | Pista [3V3] su F.Cu, lung. 0.6767 mm (-8.45; 10.24) | 3.16 mm |
| 3V3 | Piazzola 1 [3V3] di C_G0B1_FIN_VDD1 su B.Cu (6.85; 8.83) | Pista [3V3] su B.Cu, lung. 0.1000 mm (6.55; 14.55) | 5.73 mm |
| COMP_5V_RAW | Pista [COMP_5V_RAW] su F.Cu, lung. 2.0000 mm (1.00; 6.35) | Piazzola 1 [COMP_5V_RAW] di C_FIN_VM_BULK_2 su B.Cu (-1.56; 6.73) | 2.59 mm |
| COMP_5V_RAW | Piazzola 1 [COMP_5V_RAW] di C_FIN1_VM su B.Cu (-7.55; 7.70) | Piazzola 40 [COMP_5V_RAW] di J su F.Cu (-8.45; 11.84) | 4.24 mm |
| COMP_5V_RAW | Pista [COMP_5V_RAW] su F.Cu, lung. 1.0500 mm (-10.33; 2.94) | Piazzola 1 [COMP_5V_RAW] di C_FIN1_VM su B.Cu (-7.55; 7.70) | 5.51 mm |
| FLEX_GND | Pista [FLEX_GND] su F.Cu, lung. 0.1250 mm (-5.50; 9.00) | Piazzola 2 [FLEX_GND] di C_G0B1_FIN_VREF su B.Cu (-5.98; 8.38) | 0.79 mm |
| FLEX_GND | Pista [FLEX_GND] su B.Cu, lung. 1.0743 mm (-10.32; 1.10) | Pista [FLEX_GND] su F.Cu, lung. 0.9945 mm (-9.43; 0.00) | 1.42 mm |
| FLEX_GND | Pista [FLEX_GND] su B.Cu, lung. 1.6000 mm (-14.25; -1.45) | Pista [FLEX_GND] su F.Cu, lung. 1.6000 mm (-14.85; 0.64) | 2.18 mm |
| FLEX_GND | Pista [FLEX_GND] su F.Cu, lung. 0.4335 mm (8.88; 7.15) | Pista [FLEX_GND] su B.Cu, lung. 0.1500 mm (6.55; 7.70) | 2.39 mm |
| FLEX_GND | Pista [FLEX_GND] su F.Cu, lung. 0.5933 mm (5.62; -6.31) | Pista [FLEX_GND] su F.Cu, lung. 0.5267 mm (8.50; -4.47) | 3.41 mm |
| FLEX_GND | Pista [FLEX_GND] su F.Cu, lung. 0.5500 mm (-5.50; -9.94) | Pista [FLEX_GND] su F.Cu, lung. 2.6947 mm (-2.81; -6.69) | 4.22 mm |

Quasi tutte sono una **via mancante** fra due spezzoni della stessa net su strati diversi, o un piazzola che deve scendere al suo piano (FLEX_GND su In1/4/7/10/12, 3V3 su In6, COMP_5V_RAW su In2): basta una via 0,45/0,20 vicino alla piazzola.

## 3. Segnali (15)

| Net | Da | A | Distanza |
|---|---|---|---|
| FIN_HALL | Pista [FIN_HALL] su F.Cu, lung. 1.1000 mm (-2.00; 10.00) | Pista [FIN_HALL] su B.Cu, lung. 2.5022 mm (-2.39; 9.00) | 1.08 mm |
| G0B1_FIN_NRST | Pista [G0B1_FIN_NRST] su In8.Cu, lung. 1.8488 mm (-3.96; 7.48) | Pista [G0B1_FIN_NRST] su F.Cu, lung. 0.1250 mm (-5.00; 9.00) | 1.84 mm |
| COMP_SWDIO | Piazzola 10 [COMP_SWDIO] di P su B.Cu (11.35; -6.25) | Piazzola 15 [COMP_SWDIO] di J su F.Cu (12.35; -4.16) | 2.32 mm |
| EXT_CAN_TX | Piazzola 14 [EXT_CAN_TX] di P su B.Cu (9.75; -4.65) | Piazzola 17 [EXT_CAN_TX] di J su F.Cu (12.35; -7.36) | 3.75 mm |
| FIN4_BOUT2 | Piazzola 5 [FIN4_BOUT2] di U_FIN4 su F.Cu (1.00; 8.95) | Piazzola 28 [FIN4_BOUT2] di P su B.Cu (3.35; 12.95) | 4.64 mm |
| COMP_INP | Piazzola 1 [COMP_INP] di U_COMP_PZ su F.Cu (8.45; 7.50) | Piazzola 2 [COMP_INP] di R_COMP_SER su F.Cu (8.50; 1.52) | 5.98 mm |
| ACTIVATE_SET | Piazzola 4 [ACTIVATE_SET] di J su F.Cu (13.95; 0.64) | Piazzola 4 [ACTIVATE_SET] di P su B.Cu (14.55; -6.25) | 6.92 mm |
| FIN2_DVDD | Piazzola 1 [FIN2_DVDD] di C_FIN2_DVDD su B.Cu (-7.53; 10.00) | Piazzola 8 [FIN2_DVDD] di U_FIN2 su F.Cu (-5.78; 2.94) | 7.28 mm |
| COMP_OUT | Piazzola 4 [COMP_OUT] di U_COMP_PZ su F.Cu (9.49; 6.80) | Piazzola 13 [COMP_OUT] di J su F.Cu (12.35; -0.96) | 8.27 mm |
| SYS_I2C_SDA | Piazzola 42 [SYS_I2C_SDA] di P su B.Cu (-4.65; 12.95) | Piazzola 30 [SYS_I2C_SDA] di J su F.Cu (5.95; 13.44) | 10.61 mm |
| FIN2_BEN | Piazzola 13 [FIN2_BEN] di U_FIN2 su F.Cu (-8.38; -2.94) | Pista [FIN2_BEN] su F.Cu, lung. 0.1250 mm (-3.50; 10.00) | 13.83 mm |
| FIN1_BPH | Piazzola 12 [FIN1_BPH] di U_FIN1 su F.Cu (0.38; -7.99) | Pista [FIN1_BPH] su F.Cu, lung. 1.2000 mm (-3.75; 7.08) | 15.62 mm |
| FIN1_APH | Piazzola 14 [FIN1_APH] di U_FIN1 su F.Cu (0.38; -9.29) | Piazzola H5 [FIN1_APH] di U_G0B1_FIN su F.Cu (-3.50; 10.50) | 20.16 mm |
| FIN3_BPH | Pista [FIN3_BPH] su F.Cu, lung. 0.1250 mm (-4.00; 8.50) | Piazzola 12 [FIN3_BPH] di U_FIN3 su F.Cu (8.44; -8.18) | 20.80 mm |
| I2C3_SDA | Piazzola 37 [I2C3_SDA] di P su B.Cu (-1.45; 12.95) | Piazzola 25 [I2C3_SDA] di J su F.Cu (10.75; -4.16) | 21.01 mm |

## Note

- **FIN2_DVDD**: il condensatore C_FIN2_DVDD è a 7,3 mm dal pin 8 di U_FIN2: il datasheet DRV8428E lo vuole vicino al pin. Conviene avvicinarlo prima di sbrogliarlo.
- **FIN1_APH, FIN3_BPH, I2C3_SDA** sono i più lunghi (20–21 mm): passano mezza scheda, meglio su uno strato interno (In3/In5/In8).
- I pin SWD dell'STM32 (PA13/PA14) restano non collegati (decisione aperta).
