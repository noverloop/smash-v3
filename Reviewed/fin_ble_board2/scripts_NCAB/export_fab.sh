#!/bin/bash
# Pacchetto di fabbricazione NCAB della fin_ble_board (solo lettura della scheda)
# Uso: bash export_fab.sh <cartella progetto> <cartella output>
K="/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"; PRJ="$1"; OUT="$2"; N=fin_ble_board; PCB="$PRJ/$N.kicad_pcb"
mkdir -p "$OUT"
CU="F.Cu"; for i in $(seq 1 12); do CU="$CU,In$i.Cu"; done; CU="$CU,B.Cu"
"$K" pcb export gerbers -o "$OUT" -l "$CU,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts" "$PCB"
"$K" pcb export drill -o "$OUT/" --format excellon -u mm --excellon-zeros-format decimal --excellon-oval-format route \
  --excellon-separate-th --drill-origin absolute --generate-map --map-format pdf \
  --generate-report --report-path "$OUT/$N-drill_report.txt" "$PCB"
"$K" pcb export ipcd356 -o "$OUT/$N.d356" "$PCB"
"$K" pcb drc --format report --severity-all --refill-zones -o "$OUT/$N-DRC.rpt" "$PCB"
