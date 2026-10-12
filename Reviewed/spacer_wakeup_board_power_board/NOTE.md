# spacer_wakeup_board_power_board — straight-through via spacer (generated 2026-10-12)

**Fab intent: vias only.** Every LGA land on the top face has a land on the bottom face at the
same position on the same net, joined by ONE filled, capped and plated-over through-via under the
land. Nothing else: no inner layers, no planes or pours, no tracks — no routing on the top or the
bottom face. 2 copper layers (F.Cu / B.Cu = the land faces).

- lands: 65 per face, 54 distinct nets; vias: 65 (one per land, same net)
- board thickness in file: 4.3 mm; outline Ø34 mm with the routed through-window(s) on Edge.Cuts and 2 × Ø3.0 NPTH potting holes
- see `spacer_wakeup_board_power_board_cam.md` (if present) and the Gerbers in this folder for the fab data

## Mates
- top face: `Reviewed/wakeup_board 2/wakeup_board.kicad_pcb` (`J_wakeup_board_spacer_wakeup_board_power_board`) — mates 65/65 lands, 65 nets match
- bottom face: `Reviewed/power_board_generated/power_board.kicad_pcb` (`P_power_board_spacer_wakeup_board_power_board`) — mates 65/65 lands, 65 nets match
  (power board and everything above it sit rotated 180° about the stack axis; the fold is accounted for)
