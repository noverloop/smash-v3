# fin_ble_board2 — wakeup-side LGA lands moved (2026-10-12)

Base: `Review/fin_ble_board2` (copied unchanged; this file + 10 pad positions are the only edits).

## Why
The spacer between fin_ble_board and wakeup_board (`spacer_fin_ble_board_wakeup_board`) needs a
through-window to clear the wakeup board's bottom-side parts (C_IR_WAKE, RPU_IR_WAKE, C_CAM_VDD).
That window reached into lands 21, 22, 23 and 53, leaving part of their copper over the cutout
(no FR4 under it). Moving the lands away from those parts keeps every land fully on FR4 with
≥ 0.30 mm to the window edge. The generator's pinned field
(`application/src/smash/data/fin_ble_board_ee_lands.json`) already carries these positions, so the
generated spacer and wakeup_board match this board.

## Land moves — footprint `J_fin_ble_board_spacer_fin_ble_board_wakeup_board` (F.Cu, at 0,0)
| Pad | Net | Before (x, y) | After (x, y) |
|-----|-----|---------------|--------------|
| 3  | ACTIVATE_CONFIRM | 13.95, 2.241  | 14.35, 2.241  |
| 4  | ACTIVATE_SET     | 13.95, 0.641  | 14.35, 0.641  |
| 5  | BAT_CELL1_POS    | 13.95, -0.959 | 14.35, -0.959 |
| 11 | COMP_5V          | 12.35, 2.241  | 12.75, 2.241  |
| 12 | COMP_5V_RAW      | 12.35, 0.641  | 12.75, 0.641  |
| 13 | COMP_OUT         | 12.35, -0.959 | 12.75, -0.959 |
| 21 | GPIO_EXT_2       | 10.75, 2.241  | 11.15, 2.241  |
| 22 | GPIO_EXT_3       | 10.75, 0.641  | 11.15, 0.641  |
| 23 | H3LIS_INT1       | 10.75, -0.959 | 11.15, -0.959 |
| 53 | FLEX_GND         | -11.65, -5.759 | -11.65, -6.759 |

Rows (3,11,21), (4,12,22), (5,13,23) shift +0.40 mm in x (away from the centre); land 53 moves
1.0 mm up. The wakeup_board bottom field (`P_wakeup_board_spacer_fin_ble_board_wakeup_board`) must
make the identical moves — same KiCad frame for this joint.

## TO DO before fab — routing NOT yet updated
Only the pads were moved; the copper still follows the old positions. KiCad DRC (board rules)
vs the original: 7 shorts, 3 clearance, 3 hole-clearance, 8 solder-mask-bridge errors, 1 unconnected.
Re-route on F.Cu around the new land positions:
- pad 4 (ACTIVATE_SET) sits on a COMP_5V_RAW track + via
- pads 5 (BAT_CELL1_POS) and 13 (COMP_OUT) sit on a BAT_CELL3_POS track + via
- pads 22 (GPIO_EXT_3) and 23 (H3LIS_INT1) sit on an I2C3_SCL track
- pad 53 (FLEX_GND) sits on a BAT_PROT via; its own 1.6 mm FLEX_GND track is now unconnected
- reconnect each moved land's own stub to its new position
