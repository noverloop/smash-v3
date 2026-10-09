# Review wakeup_board (Sjoert de Boer) – risposte dell'autore, 2026-10-05

File: `Review Record_WakeUp2_Fransesco.xlsm`, foglio **Review Results**, righe 8–15.
Codici colonna **Action**: `a` = accepted, `r` = rejected (motivare nel Remark), `d` = deferred.
La colonna **Check** è del moderatore: lasciarla vuota.

Stato scheda dopo le correzioni: DRC 0 unconnected, 0 errors, 0 warnings (20 exclusions, giustificate).

| Riga | Issue (Sjoert) | Action | Remark (da incollare) |
|---|---|---|---|
| 8 | Overlapping silk and copper | **r** | Rejected – no silkscreen is manufactured (NCAB, no legend print); silkscreen layers are not included in the fab data. Silkscreen DRC checks set to ignore. |
| 9 | 3D models of footprints are not correctly placed in the library | **a** | Fixed – inductors L_PWR/L_WBA_SMPS given 3D models; misplaced vendor models (sunk/offset/flipped) replaced with KiCad standard SOT-23 / SOT-23-5 / DFN-6 models (same pinout as our footprints) or re-aligned (RR123); project library footprints updated accordingly. Test points, LGA spacer lands and potting holes intentionally have no 3D model. |
| 10 | Net REG_IN_MAIN should be rerouted | **a** | Fixed – In9 power-path zones rebuilt with smooth outlines (REG_IN_MAIN plane ~310 mm², orphan BOOST_OUT island merged); REG_IN_MAIN tracks widened to 0.4 mm where space allows (59/69 segments). Remaining short necks (≤0.187 mm) near U_WBA / L_PWR run parallel to the In9 REG_IN_MAIN plane. |
| 11 | Use teardrops | **a** | Fixed – teardrops added on all vias, microvias, PTH and SMD pads (L 50 %/max 0.5 mm, W 100 %/max 1 mm, curved, prefer zone connections). |
| 12 | Each FLEX_GND should have its own microvia or via | **a** | Fixed – 24 microvias added (19 via-in-pad, 5 next to pad): 112/114 FLEX_GND SMD pads now have their own via (F.Cu–In1 or In12–B.Cu into the GND planes). U_WBA D13/G6 (0.35 mm WLCSP): In1 under these balls is used for fan-out; grounded through adjacent GND balls on F.Cu. |
| 13 | Some vias only connect in the annular ring which should be avoided | **a** | Fixed – the only case (REG_IN_MAIN via touching U_BOOST pin 3 with its ring, no track) was redundant: pin 3 = EN, already tied to REG_IN_MAIN by two F.Cu tracks; via removed. Four undersized vias (0.40 mm) near U_WBA enlarged to 0.45/0.20 (NCAB minimum). |
| 14 | Check layout for acid traps --> there are a lot | **a** | Fixed – In9 stair-step zone edges (0.2 mm raster) replaced by straight/rounded outlines; 9 acute track corners chamfered; 12 overlapping (doubled) track segments and dangling stubs removed. Remaining 13 acute corners are at pad/via entries (wedge filled by pad/via copper and teardrops) or T-junctions. |
| 15 | Edge Cuts layer seems not to be an arc, check it | **a** | Fixed – board outline was 90 line segments (chords of R17, up to 0.12 mm inside the circle); replaced by a true circle R17 mm. |

## Riepilogo in italiano

1. **Serigrafia sopra il rame**: rifiutato con motivazione, perché NCAB non stampa serigrafia.
2. **Modelli 3D**: induttori aggiunti; i modelli SOT/DFN sbagliati sono stati sostituiti con quelli standard KiCad; RR123 riallineato; libreria aggiornata.
3. **REG_IN_MAIN**: In9 lisciato; piste allargate a 0.4 mm dove c'è spazio (59 su 69).
4. **Teardrop**: aggiunte ovunque.
5. **Via GND proprie**: 24 microvia nuove, 112 pad su 114 coperti; D13 e G6 di U_WBA sono giustificati.
6. **Via solo sull'anello**: la via di U_BOOST.3 era ridondante ed è stata tolta; le 4 via da 0.40 sono state portate a 0.45.
7. **Acid trap**: In9 senza scalette; 9 angoli smussati; piste doppie e pezzetti pendenti tolti.
8. **Edge.Cuts**: ora è un cerchio vero R17.

Backup di ogni passaggio: cartelle `backup_pre_*_20261005` nel progetto. Script: `scripts_NCAB/` (in9_smooth, edge_overlap, gnd_vias, via_off_pad, widen_net, fix_acute, fix_3d).
