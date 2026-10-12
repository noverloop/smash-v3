# spacer_battery_4 — straight-through via spacer (generated 2026-10-12)

**Fab intent: vias only.** Every LGA land on the top face has a land on the bottom face at the
same position on the same net, joined by ONE filled, capped and plated-over through-via under the
land. Nothing else: no inner layers, no planes or pours, no tracks — no routing on the top or the
bottom face. 2 copper layers (F.Cu / B.Cu = the land faces).

- lands: 60 per face, 46 distinct nets; vias: 60 (one per land, same net)
- board thickness in file: 3.5 mm; outline Ø34 mm with the routed through-window(s) on Edge.Cuts and 2 × Ø3.0 NPTH potting holes
- see `spacer_battery_4_cam.md` (if present) and the Gerbers in this folder for the fab data

## Mates
- top face: `spacer_battery_3` (stacked spacer — identical land field)
- bottom face: `spacer_battery_5` (stacked spacer — identical land field)

Replaces `Review/spacer_battery_4`: that spacer is also straight-through, but it is a 4-layer board with an inner
FLEX_GND fill, a floating fill on the retired `GND` net and dangling off-land vias, and its land field only fits the
older cell_floor_board; its 19 vias under FLEX_GND lands are labelled with the retired `GND` net.

Battery-column spacer: the six battery spacers carry the same 60-land field, so the column passes every net straight from cell_floor_board to fin_ble_board.
