# power_board_generated — wakeup-side LGA lands moved (2026-10-12)

Base: `WIP/Sjoert/power_board_generated` (Sjoert's routed board, 2026-09-28; copied unchanged —
this file + 12 pad positions are the only edits).

## Why
The spacer between wakeup_board and power_board (`spacer_wakeup_board_power_board`) needs a
through-window to clear this board's bottom-side parts. Lands 40–43 ended exactly at the window
edge (next to L_BOOST_COMP) and lands 32–33 had only 0.08 mm of FR4 beside them (next to
C_USB_VBUS_3/4) — inside the ±0.1 mm routing tolerance. Moving them gives every land ≥ 0.40 mm of
FR4 to the window edge and ≥ 0.55 mm to the nearest part courtyard on either board.

Note: in the stack the power board and everything above it are installed rotated 180° about the
stack axis relative to the wakeup board (the potting holes are 180°-symmetric), so directions on
the spacer map to this board as: spacer "right" = +x here, spacer "down" = −y here.

## Land moves — footprint `P_power_board_spacer_wakeup_board_power_board` (B.Cu, at 0,0)
| Pad | Net | Before (x, y) | After (x, y) |
|-----|-----|---------------|--------------|
| 32 | IR_WAKE        | 0.45, -11.841  | 0.45, -12.241  |
| 33 | MAG_DRDY       | 2.05, -11.841  | 2.05, -12.241  |
| 34 | MAIN_SW_GATE   | 3.65, -11.841  | 3.65, -12.241  |
| 40 | SYS_I2C_SDA    | 10.05, -10.241 | 10.45, -10.241 |
| 41 | SYS_SPI_CS_FIN | 10.05, -8.641  | 10.45, -8.641  |
| 42 | SYS_SPI_MISO   | 10.05, -7.041  | 10.45, -7.041  |
| 43 | SYS_SPI_MOSI   | 10.05, -5.441  | 10.45, -5.441  |
| 44 | SYS_SPI_SCLK   | 11.65, -8.641  | 12.05, -8.641  |
| 45 | USBWK_GATE     | 11.65, -7.041  | 12.05, -7.041  |
| 46 | WBA_BOOT0      | 11.65, -5.441  | 12.05, -5.441  |
| 50 | WBA_HCI_NSS    | 13.25, -7.041  | 13.65, -7.041  |
| 51 | WBA_HCI_SCK    | 13.25, -5.441  | 13.65, -5.441  |

Rows (43,46,51), (42,45,50), (41,44), (40) shift +0.40 mm in x; row (32,33,34) shifts 0.40 mm in −y.
Matches the generator's pinned field (`application/src/smash/data/power_board_ee_lands.json`) and
`Reviewed/wakeup_board 2` (its top lands make the same moves in its own frame). This copy mates the
generated wakeup↔power spacer 65/65 and still mates the companion spacer 66/66, every net matching.

## TO DO before fab — routing NOT yet updated
Only the pads were moved. Every moved land still touches its own stub (DRC: 0 unconnected, 0
shorts), but KiCad DRC (board rules) vs the original adds: clearance 0 → 2, hole-clearance 0 → 1,
solder-mask-bridge 8 → 10.
- pad 43 (SYS_SPI_MOSI) is too close to a WBA_BOOT0 blind via (Layer 6 → Bottom)
- pad 51 (WBA_HCI_SCK) is too close to a COMP_5V_RAW track on Bottom
- re-centre each moved land's stub on its new position

The exports in this folder (`gerbers/`, `power_board_gerbers.zip`, `*.step`, `*.stl`,
`power_board_layered.json`) date from 2026-09-03 and predate both Sjoert's 2026-09-28 routing and
this change — re-export after re-routing.
