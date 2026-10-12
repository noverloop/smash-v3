# wakeup_board 2 — fin_ble-side LGA lands moved (2026-10-12)

Base: `WIP/Finalized from Francesco/wakeup_board 2` (copied unchanged except the stale KiCad lock
file `~wakeup_board.kicad_pro.lck`, which was left out; this file + 10 pad positions are the only edits).

## Why
The spacer between fin_ble_board and wakeup_board (`spacer_fin_ble_board_wakeup_board`) needs a
through-window to clear this board's bottom-side parts (C_IR_WAKE, RPU_IR_WAKE, C_CAM_VDD). That
window reached into lands 21, 22, 23 and 53, leaving part of their copper over the cutout (no FR4
under it). Moving the lands away from those parts keeps every land fully on FR4 with ≥ 0.30 mm to
the window edge. Same moves as `Reviewed/fin_ble_board2` (same KiCad frame for this joint) and the
generator's pinned field (`application/src/smash/data/fin_ble_board_ee_lands.json`): both reviewed
copies mate the generated spacer 69/69, every net matching.

## Land moves — footprint `P_wakeup_board_spacer_fin_ble_board_wakeup_board` (B.Cu, at 0,0)
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

## TO DO before fab — routing NOT yet updated
Only the pads were moved; the copper still follows the old positions. KiCad DRC (board rules)
vs the original: shorts 0 → 9, clearance 2 → 5, hole-clearance 0 → 2, solder-mask-bridge 0 → 9,
unconnected 0 → 1. Re-route on B.Cu around the new land positions:
- pad 5 (BAT_CELL1_POS) sits on a BAT_RAW via; BAT_CELL2_POS via too close
- pad 12 (COMP_5V_RAW) sits on a COMP_5V track and a GPIO_EXT_3 track
- pad 13 (COMP_OUT) sits on a GPIO_EXT_3 via + tracks
- pads 22 (GPIO_EXT_3) and 23 (H3LIS_INT1) sit on COMP_5V_RAW tracks
- pad 53 (FLEX_GND) — its own 0.52 mm FLEX_GND track is now unconnected
- reconnect each moved land's own stub to its new position

The fab package in this folder (`fab_NCAB_20260918/`, `wakeup_board_fab_NCAB_20260918.zip`,
`gerbers/`, `wakeup_board_gerbers.zip`) predates this change — re-export after re-routing.

---

# Power-side LGA lands moved (2026-10-12, second change)

## Why
The spacer between wakeup_board and power_board (`spacer_wakeup_board_power_board`) needs a
through-window to clear the power board's bottom-side parts. Lands 40–43 ended exactly at the
window edge (L_BOOST_COMP) and lands 32–33 had only 0.08 mm of FR4 (C_USB_VBUS_3/4). Moving them
gives every land ≥ 0.40 mm of FR4 to the window edge and ≥ 0.55 mm to the nearest courtyard on
either board. Same moves as `Reviewed/power_board_generated` and the generator's pinned field
(`application/src/smash/data/power_board_ee_lands.json`).

This board is mirrored in x relative to the spacer, so spacer "right" = −x here and spacer
"down" = +y here.

## Land moves — footprint `J_wakeup_board_spacer_wakeup_board_power_board` (F.Cu, at 0,0)
| Pad | Net | Before (x, y) | After (x, y) |
|-----|-----|---------------|--------------|
| 32 | IR_WAKE        | -0.45, 11.841  | -0.45, 12.241  |
| 33 | MAG_DRDY       | -2.05, 11.841  | -2.05, 12.241  |
| 34 | MAIN_SW_GATE   | -3.65, 11.841  | -3.65, 12.241  |
| 40 | SYS_I2C_SDA    | -10.05, 10.241 | -10.45, 10.241 |
| 41 | SYS_SPI_CS_FIN | -10.05, 8.641  | -10.45, 8.641  |
| 42 | SYS_SPI_MISO   | -10.05, 7.041  | -10.45, 7.041  |
| 43 | SYS_SPI_MOSI   | -10.05, 5.441  | -10.45, 5.441  |
| 44 | SYS_SPI_SCLK   | -11.65, 8.641  | -12.05, 8.641  |
| 45 | USBWK_GATE     | -11.65, 7.041  | -12.05, 7.041  |
| 46 | WBA_BOOT0      | -11.65, 5.441  | -12.05, 5.441  |
| 50 | WBA_HCI_NSS    | -13.25, 7.041  | -13.65, 7.041  |
| 51 | WBA_HCI_SCK    | -13.25, 5.441  | -13.65, 5.441  |

With both changes this copy mates the generated wakeup↔power spacer 65/65 and the
fin_ble↔wakeup spacer 69/69, every net matching.

## TO DO before fab — routing NOT yet updated (F.Cu)
KiCad DRC vs the copy after the first change: shorts 9 → 14, clearance 5 → 13,
solder-mask-bridge 9 → 16. Re-route on F.Cu around the new positions:
- pad 34 (MAIN_SW_GATE) sits on a MAG_DRDY track
- pad 40 (SYS_I2C_SDA) sits on a COMP_5V_RAW track (6.8 mm run)
- pad 41 (SYS_SPI_CS_FIN) too close to SYS_SPI_SCLK tracks
- pad 42 (SYS_SPI_MISO) sits on a USBWK_GATE track
- pad 43 (SYS_SPI_MOSI) sits on a REG_IN_MAIN track
- pad 45 (USBWK_GATE) too close to a WBA_BOOT0 via and a FLEX_GND via
- re-centre each moved land's stub on its new position
