#!/usr/bin/env bash
# Pacchetto di fabbricazione NCAB per wakeup_board (14 strati HDI)
# Uso: export_fab.sh <cartella_progetto> <cartella_output>
set -euo pipefail
K="/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"
PRJ="$1"; OUT="$2"
PCB="$PRJ/wakeup_board.kicad_pcb"
mkdir -p "$OUT"
CU="F.Cu"; for i in $(seq 1 12); do CU="$CU,In$i.Cu"; done; CU="$CU,B.Cu"
# serigrafia esclusa: PCB Info Sheet NCAB "Top/Bottom silkscreen: No"
"$K" pcb export gerbers -o "$OUT" -l "$CU,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts" "$PCB"
"$K" pcb export drill -o "$OUT/" --format excellon -u mm --excellon-zeros-format decimal \
     --excellon-oval-format route --excellon-separate-th --drill-origin absolute \
     --generate-map --map-format pdf --generate-report --report-path "$OUT/wakeup_board-drill_report.txt" "$PCB"
"$K" pcb export ipcd356 -o "$OUT/wakeup_board.d356" "$PCB"
"$K" pcb drc --format report --severity-all --refill-zones -o "$OUT/wakeup_board-DRC.rpt" "$PCB"
