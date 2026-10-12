# activation_interface — STATO LAVORO (documento unico, aggiornato ad ogni passo)

> File: `G:\activation_interface\activation_interface.kicad_pcb` (generator "smash", KiCad 10, version 20260206).
> Regole layout dai datasheet: `G:\activation_interface\LAYOUT_NOTES_da_datasheet.md`. Datasheet in `G:\activation_interface\datasheets\`.

## Cos'è la scheda
Interposer **tondo R17** (Ø34), **14 layer**, famiglia **smash** impilata (spaziatori J→cell_floor_board sopra, P→aft_end_board sotto). Componenti attivi sul **Top (F.Cu)**. Net name-based `(net "NOME")`.

### Circuito
- **FIRE = boost ~33V** (attivazione): U_FIRE_BOOST=**TPS61175PWPR**, L_FIRE=744043100(10µH), D_FIRE=MBRS540(Schottky 40V/5A), C_FIRE_IN×5 (da COMP_5V), C_FIRE_OUT×2 (FIRE_HV), R_FB1/FB2=261k/10k → **Vout=33.3V**, R_FREQ=176k → **fSW=600kHz**, R_COMP/C_COMP/C_SS(47nF).
- **HACC = accel high-g**: U_HACC=**H3LIS331DL** (±100-400g), C_HACC1(100nF)+C_HACC2×5, I2C3 + H3LIS_INT1.
- **Connettori interposer** J/P (LGA lands): ~40 segnali pass-through.

## VINCOLI (NON ridirmeli — sono qui)
1. **Placement**: i componenti DEVONO stare dentro il **keep-out del F.Silkscreen** (tratteggio giallo = area utile rigida). Densità al centro = VOLUTA, non spostare i componenti. (come wake_board, regola famiglia smash)
2. **Leggere i datasheet/AN PRIMA di layout** (fatto: TPS §10, H3LIS §4, TN0018). Vedi LAYOUT_NOTES.
3. **KiCad va CHIUSO** per editare il file via script (hand-edit `(net "NOME")` ok, validato con kicad-cli). Riaprire dopo.
4. Consegnare/aggiornare sempre questo .md + path Windows completi.

## Net di potenza
FLEX_GND (192 pad), 3V3 (16), COMP_5V (12, ingresso boost), FIRE_HV (6, ~33V HV), BAT_RAW/BAT_PROT/3V3_AON (4 ea), FIRE_SW (nodo switch — NON piano, loop compatto).

## PIANI — FATTO ✓
Stackup smash ha già i ruoli: **In1/In2/In11/In12 = "power"**, resto signal. Allocazione disegnata (zone circolari R16.5):
- **In1 = FLEX_GND** (+ keepout sotto U_HACC per TN0018)
- **In2 = 3V3**
- **In11 = COMP_5V**
- **In12 = FLEX_GND**
FIRE_HV/BAT/3V3_AON/FIRE_SW = tracce (non piani). Script `scratchpad/make_planes_ai.py`. Backup `.bak_preplanes_1788102500`. 0 nuovi problemi DRC.

## ROUTING — in corso
**Il mio router da script NON funziona** (linee dirette senza obstacle-avoidance → short/incroci; via in-pad su pad fitti → clearance/mask). Provato: +10 short, 3 incroci, 46 hole_clr → RIPRISTINATO. Backup tentativo: `.bak_preroute_1788103470`.
**SI USA il plugin Freerouting di KiCad** (GIÀ INSTALLATO, "KiCad Freerouting Plugin", usa Java 25 ✓). Fa: Detecting Java → Starting Freerouting API → Sending board → Auto-router → Receiving results. È l'autorouter VERO (push&shove/ripup), non-HDI quindi ok.
- Piano: Freerouting fa il routing DRC-pulito di tutto, POI **ottimizziamo a mano solo lo stadio boost** (TPS §10: hot loop SW compatto, FB lontano da SW, thermal pad→via a In1, Cin vicino a VIN). NB il boost è SPARSO (L a sx, IC in alto, D in basso) → SW attraversa il centro, non è compatto (placement vincolato).

## ✅ RISOLTO (2026-08): errore Freerouting "designator" = footprint senza reference
Freerouting/export DSN falliva con "...provare ... **designator**" perché **2 footprint "smash_mech:potting" avevano Reference vuoto**. **FIX FATTO:** assegnati `MECH1`/`MECH2` (script inline, backup `.bak_mechref_*`). 0 reference vuoti, kicad-cli parse OK. → **rilanciare il plugin Freerouting.**

## FREEROUTING PARTITO (2026-08) ✅
Dopo il fix MECH1/MECH2, il plugin ha esportato il DSN e **Freerouting v2.3.0 sta routando** (board tonda caricata, tracce rosse sui connettori, ratsnest al centro). Denso al centro (boost+accel nel keep-out) → possibili net non routati lì.
**Per riportare in KiCad:** o il plugin importa da solo alla fine ("Receiving the results"), o manuale: Freerouting `File → Export Specctra Session File` (.ses in G:\activation_interface) → KiCad `File → Importa → Specctra Session`.
**DOPO l'import:** DRC + **ottimizzare a mano lo stadio boost** (hot loop SW, FB lontano da SW, via thermal pad → In1, Cin vicino a VIN — TPS §10). Poi accel (I2C/decoupling/keepout), poi fill + DRC finale.

## ⛔→✅ FREEROUTING 1° GIRO: DRC-dirty (regole sbagliate) → RIFATTA la DRU NCAB
1° import Freerouting: 619 seg, 74 via, 22 unrouted MA **~580 violazioni NUOVE** (clearance 293, hole_clearance 201, annular 74, track_width 17). Causa: netclass era **via 0.3/0.15** (annular 0.075 < min 0.1) e **nessun .kicad_dru** → Freerouting ha usato regole non-NCAB.
**RISOLTO:** ripristinati piani puliti (da `.bak_mechref_*`), scritto **`activation_interface.kicad_dru` NCAB** (via-track 150, micro-micro 150, micro-buried 250 foro, buried-buried 300, mech drill 200/pad 450, microvia capture 250), e **netclass NCAB** nel .kicad_pro: **via 0.45/0.2** (annular 0.125), microvia 0.25/0.1, track 0.1, clearance 0.075, min annular 0.1. DRC base ripulito (solo pre-esistenti smash: 17 short footprint, 21 mask, 19 mismatch).
**CAVEAT:** via NCAB 0.45 > 0.3 usate prima → centro denso ancora più stretto; potrebbero servire microvie (0.25/0.1) nel centro.

**NB ERRORE MIO (corretto):** ripristinando `.bak_mechref_*` ho riportato i reference VUOTI (il backup è PRE-fix, fatto prima di applicare MECH1/MECH2) → Freerouting ridava "empty reference designator". Ri-applicati MECH1/MECH2 sul file corrente (backup `.bak_mechref2_*`). **Lezione: i backup `.bak_*` sono lo stato PRIMA della modifica di quello script — non ripristinarli aspettandosi il fix.**

## FREEROUTING 2° GIRO (NCAB) — routato, poi DRU rilassata (NON-HDI)
2° giro: 644 seg, ~72 via, autoroute finito a **24 unrouted / 30 violazioni**. **⚠️ L'ottimizzatore multi-thread di Freerouting è ROTTO** (avviso nel log: "generates clearance violations, use -mt 1") → ha gonfiato a ~550 nel mio kicad-cli. MA il **DRC GUI (con zone riempite) = 146 errori**, e **quasi tutti erano la mia regola custom "via-track 150µm"** (Freerouting non conosce il .dru, ha routato a clearance 0.075).
**DECISIONE utente: questo NON è un HDI design** → **rilassata la DRU**: `.kicad_dru` ora ha SOLO via meccanica (drill≥0.2/pad≥0.45); rimosse via-track 150 + microvia/buried (HDI-specifiche). Via-track ora usa la clearance netclass (0.075). DSN esportati in `%TEMP%\freerouting\kicad\`.
**Net completamente non routati (0 tracce): solo 3** → FIRE_COMP, FIRE_FREQ, FIRE_SS (segnali comp boost, centro denso). Gli altri 39 hanno tracce.

## STATO A FINE GIORNATA (2026-08-30) — RIPRENDERE DA QUI
Dopo aver rilassato il .dru (tolta via-track 150), **DRC KiCad = 77 errori** (giù da 146), + 45 avvisi + **20 non connessi**.
**I 77 errori sono QUASI TUTTI DIFETTI DI FOOTPRINT, non routing:**
- "Elementi che cortocircuitano" tra **pin adiacenti di U_FIRE_BOOST** (TPS61175: FIRE_SW/COMP_5V/FIRE_SS/FLEX_GND pin 1-2-3-4...) e **U_HACC** (accel): i pad si TOCCANO (clearance reale 0.000mm). Sono gli stessi 17 short + 19 footprint_mismatch presenti DALL'INIZIO con 0 tracce → **impronte smash con pad sovrapposti**. Il board li avrebbe comunque. NON sono nostri.
- + 21 solder_mask_bridge + silk pre-esistenti smash.
**Il ROUTING è ~pulito** (le violazioni vere di routing sono sparite col fix netclass NCAB + DRU rilassata).
**20 non connessi** = net boost da finire a mano: **FIRE_COMP, FIRE_FREQ, FIRE_SS** (3 net 0-tracce) + alcune via ai piani (COMP_5V→In11, ecc.).

## DA FARE DOMANI (in ordine)
1. **Footprint difettosi TPS61175 + H3LIS331DL**: verificare l'overlap reale dei pad (clearance 0.000 = pad che si toccano) → o sostituire con footprint corretti di libreria / correggere i pad, **oppure segnalare a Nicolas** (è un problema smash a monte: short reali in produzione). DECIDERE questo prima di rifinire.
2. **Finire il routing del boost a mano** (KiCad interattivo, TPS §10): FIRE_COMP/FREQ/SS + via ai piani + rifinire hot loop SW (compatto) + FB lontano da SW + via array sul thermal pad → In1.
3. **DRC finale** (solo i difetti footprint dovrebbero restare, da girare a Nicolas) + fill zone.

## PROMEMORIA TECNICI (per non ripetere)
- **KiCad va CHIUSO** per editare il file via script; riaprire dopo. I `.bak_*` sono lo stato PRIMA della modifica di quello script (non ripristinarli aspettando il fix — vedi errore MECH).
- **Netclass NCAB**: via 0.45/0.2 (annular 0.125), microvia 0.25/0.1, track 0.1, clearance 0.075. **.kicad_dru**: solo mech via drill≥0.2/pad≥0.45 (rimosse le HDI: via-track 150, microvia/buried — NON è un HDI design).
- **Freerouting**: plugin KiCad OK, ma **ottimizzatore multi-thread ROTTO** (genera clearance violations) → se si ri-routa usare **single-thread**. DSN in `%TEMP%\freerouting\kicad\`.
- Backups: `.bak_preplanes_*`, `.bak_mechref2_1788104xxx` (piani+NCAB+MECH, PRE-freerouting). Piani: In1/In12=FLEX_GND, In2=3V3, In11=COMP_5V.
2. Freerouting autoroute → scheda routata DRC-pulita.
3. Ottimizzare a mano lo stadio boost (TPS §10) + via thermal pad.
4. Verificare accel (I2C, decoupling, keepout sotto).
5. DRC finale + fill.

## Backups / file
- `.bak_preplanes_1788102500` (pre-piani), `.bak_preroute_1788103470` (pre-routing tentativo).
- Script: `scratchpad/make_planes_ai.py`, `route_boost.py` (scartato).
- Konnect MCP: IPC ok (socket `...Temp\kicad\api.sock`), ma tool routing con glitch dopo riavvio → si usa il plugin Freerouting in KiCad.

## FIX FOOTPRINT DIFETTOSI (2026-09-02) — pad che si toccavano
Entrambi i footprint smash avevano le piazzole col **lato lungo orientato lungo il pitch** (invece che radiale) → pad adiacenti sovrapposti → short. Corretti a KiCad chiuso, con backup, verificati DRC:
- **U_HACC (LIS3DHTR LGA-16)**: pad colonne sx (1-5) e dx (9-13) da 0.3×0.6 → **0.6×0.3** (lato lungo radiale, corto 0.3 lungo il pitch 0.5 → gap 0.2). Land ora **simmetrico su 4 lati** (richiesto da TN0018: "footprint simmetrico, land uguali"). Risolti 12 short/mask-bridge. Backup `.bak_preHACCpadfix_1788341524`.
- **U_FIRE_BOOST (TPS61175, SOP65P640X120-15N)**: pad 1-14 da 0.45×1.475 → **1.475×0.45** (lato lungo radiale, corto 0.45 lungo il pitch 0.65 → gap 0.20). Pad 15 (thermal) invariato. **28 short → 0, zero nuovi**. Backup `.bak_preBOOSTpadfix_1788343804`.

**Metodo (per i prossimi footprint smash difettosi):** la size è giusta ma **w/h sono scambiati** sui lati dove il pitch è perpendicolare all'uscita pin → basta swappare w↔h sui pad di quei lati (scoped al blocco footprint, KiCad chiuso, backup, DRC prima/dopo in condizioni identiche).

**Board: da ~57 → 9 errori.** I 9 rimasti sono **"Larghezza pista"** (FIRE_HV, FLEX_GND, 3V3, NRST) — tracce sotto il minimo scheda, da sistemare nel routing (NON footprint). Via 3V3 nel keepout accel = errore "area proibita" (TN0018): va messa FUORI dal contorno accel.
