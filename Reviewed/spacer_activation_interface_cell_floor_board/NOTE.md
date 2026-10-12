# spacer_activation_interface_cell_floor_board — straight-through via spacer (generated 2026-10-12)

**Fab intent: vias only.** Every LGA land on the top face has a land on the bottom face at the
same position on the same net, joined by ONE filled, capped and plated-over through-via under the
land. Nothing else: no inner layers, no planes or pours, no tracks — no routing on the top or the
bottom face. 2 copper layers (F.Cu / B.Cu = the land faces).

- lands: 150 per face, 46 distinct nets; vias: 150 (one per land, same net)
- board thickness in file: 3.1 mm; outline Ø34 mm with the routed through-window(s) on Edge.Cuts and 2 × Ø3.0 NPTH potting holes
- see `spacer_activation_interface_cell_floor_board_cam.md` (if present) and the Gerbers in this folder for the fab data

## Mates
- top face: `Reviewed/activation_interface/activation_interface.kicad_pcb` (`J_activation_interface_spacer_activation_interface_cell_floor_board`) — mates 150/150 lands, 150 nets match
- bottom face: `Reviewed/cell_floor_board/cell_floor_board.kicad_pcb` (`P_cell_floor_board_spacer_activation_interface_cell_floor_board`) — mates 150/150 lands, 150 nets match

Replaces `Review/spacer_activation_interface_cell_floor_board`: that spacer is also straight-through, but it is a 4-layer board with an inner
FLEX_GND fill, a floating fill on the retired `GND` net and dangling off-land vias, and its land field only fits the
older activation_interface / cell_floor_board.
