# spacer_power_board_companion_compute — straight-through via spacer (generated 2026-10-12)

**Fab intent: vias only.** Every LGA land on the top face has a land on the bottom face at the
same position on the same net, joined by ONE filled, capped and plated-over through-via under the
land. Nothing else: no inner layers, no planes or pours, no tracks — no routing on the top or the
bottom face. 2 copper layers (F.Cu / B.Cu = the land faces).

- lands: 66 per face, 56 distinct nets; vias: 66 (one per land, same net)
- board thickness in file: 3.2 mm; outline Ø34 mm with the routed through-window(s) on Edge.Cuts and 2 × Ø3.0 NPTH potting holes
- see `spacer_power_board_companion_compute_cam.md` (if present) and the Gerbers in this folder for the fab data

## Mates
- top face: `Reviewed/power_board_generated/power_board.kicad_pcb` (`J_power_board_spacer_power_board_companion_compute`) — mates 66/66 lands, 66 nets match
- bottom face: `WIP/Sjoert/companion_compute/companion_compute.kicad_pcb` (`P_companion_compute_spacer_power_board_companion_compute`) — mates 66/66 lands, 66 nets match
  (companion_compute is not routed yet; its WIP bottom field is what the generator uses)
