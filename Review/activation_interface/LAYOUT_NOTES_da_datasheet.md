# activation_interface — Layout notes dai datasheet (letti PRIMA di routare)

Datasheet in `G:\activation_interface\datasheets\` (TPS61175.pdf, H3LIS331DL.pdf). Regola: [[feedback_leggere_datasheet_prima_layout]].

## TPS61175 (boost FIRE ~33V) — §10 Layout Guidelines (SLVS892F)
- **SW pin**: minimizzare lunghezza/area di TUTTE le tracce su SW; **piano GND sotto il regolatore**.
- **Hot loop** (switch + diodo Schottky + Cout): fronti in ns → **il più corto possibile** (è la sorgente EMI).
- **Cin** vicino sia a **VIN** sia a **PGND** (riduce ripple ingresso).
- **Thermal pad (PowerPAD) = AGND**, saldato con **via termiche sotto**; Rθja dipende dal layout; Tj ≤ 125°C.
- **FB/COMP/SS/FREQ** vicini ai rispettivi pin su AGND pulito; **rete FB lontana da SW/induttore** (Fig.17).
- Elettrico: switch 40V, Vout≤38V; **fSW=600kHz** (R_FREQ 176k, Tab.2); Vref FB 1.229V → **Vout=1.229·(1+261/10)=33.3V**; SS 47nF = no overshoot (Tab.3); Vin 2.9–18V (COMP_5V=5V ok); slope-comp ok se L≥4.7µH (L_FIRE 744043100=10µH ok).

## H3LIS331DL (accel high-g) — §4 Application hints (DocID023111 Rev3)
- **Decoupling 100nF + 10µF il più vicino possibile al pin 14 (Vdd)**.
- Vdd (core) + **Vdd_IO** (I/O) entrambi; **tutte le alimentazioni presenti insieme**.
- **I2C → CS tied high** (a Vdd_IO). Indirizzo 001100x → 0x18/0x19 via SA0. I2C fast 400kHz. Pull-up interni a Vdd_IO.
- **GND solido sotto**; pin-1 indicator NON connesso; land pattern LGA-16 da st.com.
- High-g: montare dove la scheda flette meno.

## Impatto su piani/routing
- In1 = GND (sotto F.Cu) sotto tutto il boost → riferimento hot loop. Thermal pad TPS con array di via a GND.
- Hot loop del boost TUTTO su F.Cu, compatto: Cin(x5)→VIN, SW→L_FIRE→D_FIRE→Cout(x2)→FIRE_HV.
- FB (R_FB1 261k/R_FB2 10k) e comp/freq/ss vicini ai pin, lontani da SW.
- FIRE_HV ~33V: clearance/keep-out verso gli altri net.
- HACC: 100nF (C_HACC1) + bulk (C_HACC2) vicino al pin 14; I2C3 pulito; GND solido.

## TN0018 — MEMS handling/mounting/soldering (ST, Rev 8) — per H3LIS331DL
- **Strain max vicino al sensore: 1000 µstrain.** Lontano da hot-spot (BOOST FIRE, batterie), connettori, viti, ancoraggi PCB, pushbutton (stress → errore di misura).
- **≥2mm** da connettori/feature sotto la PCB vicino al sensore. **PCB e footprint SIMMETRICI**; land tutte uguali; solder mask aperto fuori dal land (0.1mm).
- **§3.9 TOP side sotto il sensore = KEEP-OUT**: nessuna traccia, nessuna via sotto U_HACC su F.Cu. **Via fuori dall'impronta**.
- **§3.8 GND non collegato direttamente ai pad**: connettere con **traccia standard** (decoupling meccanico). "Peel cut / no GND" area sotto IC.
- **§3.10** bottom side sotto il sensore: OK piano/routing (per accel/gyro/pressure).
- LGA pad: A/B = LGA solder pad + 0.1mm (se spacing >200µm); C/D solder mask = land + 0.1mm.

### Impatto placement/planes activation_interface
1. **U_HACC lontano dal boost FIRE e dai connettori J/P** (verificare posizione attuale).
2. **Keep-out sotto U_HACC su F.Cu** (no via/tracce); via fanout accel FUORI impronta.
3. **GND sensore via traccia** (non pour diretto); footprint/tracce simmetrici.

## Fonti H3LIS331DL (fetch)
- ST datasheet (via SparkFun CDN mirror DM00053090). st.com diretto non raggiungibile da qui.
