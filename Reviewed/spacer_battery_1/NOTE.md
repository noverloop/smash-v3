# spacer_battery_1 — straight-through via spacer (generated 2026-10-12)

**Fab intent: vias only.** Every LGA land on the top face has a land on the bottom face at the
same position on the same net, joined by ONE filled, capped and plated-over through-via under the
land. Nothing else: no inner layers, no planes or pours, no tracks — no routing on the top or the
bottom face. 2 copper layers (F.Cu / B.Cu = the land faces).

- lands: 60 per face, 46 distinct nets; vias: 60 (one per land, same net)
- board thickness in file: 3.5 mm; outline Ø34 mm with the routed through-window(s) on Edge.Cuts and 2 × Ø3.0 NPTH potting holes
- see `spacer_battery_1_cam.md` (if present) and the Gerbers in this folder for the fab data

## Mates
- top face: `Reviewed/cell_floor_board/cell_floor_board.kicad_pcb` (`J_cell_floor_board_spacer_battery_1`) — mates 60/60 lands, 60 nets match
- bottom face: `spacer_battery_2` (stacked spacer — identical land field)

Battery-column spacer: the six battery spacers carry the same 60-land field, so the column passes every net straight from cell_floor_board to fin_ble_board.
