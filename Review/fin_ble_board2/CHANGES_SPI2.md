# fin_ble_board2 — SYS_SPI moved from SPI3 to SPI2

Base: `fin_ble_board` (NCAB 14L HDI, fab package 2026-10-04).

## Why
AN2606 (STM32G0B1, Table 95): the ROM bootloader accepts SPI1 (PA4–PA7) and
SPI2 (PB12–PB15) only. SYS_SPI was on SPI3 (PC10/PC11/PC12/PA15) and SWD is not
brought out, so the G0B1 could not be programmed.

## Pinout change (U_G0B1_FIN, UFBGA64)
| Net            | Before      | After        |
|----------------|-------------|--------------|
| SYS_SPI_CS_FIN | C6 / PA15   | G7 / PB12    |
| SYS_SPI_SCLK   | A2 / PC10   | G8 / PB13    |
| SYS_SPI_MISO   | A1 / PC11   | F6 / PB14    |
| SYS_SPI_MOSI   | B2 / PC12   | F7 / PB15    |
| FIN_HALL       | G8 / PB13   | H8 / PB11    |

A1, A2, B2, C6 are now unconnected. Connector pinout unchanged.

## Layout (NCAB rules, `fin_ble_board.kicad_dru`)
- BGA escape: dogbone 0.08 mm to an F.Cu→In1 microvia 0.25/0.10 (no via-in-pad),
  microvia offset 0.07 mm toward its own ball so the hole is ≥ 0.20 mm from other balls.
- Staggered buried via In1–In12 0.45/0.20 (not stacked), inner routes to the existing net copper:
  CS → In8, MOSI/MISO → In3 → In9, SCLK → In11 + In5 to the existing SCLK via.
- FIN_HALL: H8 on F.Cu to the existing FIN_HALL via.
- FIN2_BEN (In1) has a short jog between the F7 and G7 microvias.
- Short In1 segments (0.9–2 mm) cut the In1 FLEX_GND plane locally near the BGA.
- Clean-up: stair-stepped track runs and 90° corners replaced by 45° segments board-wide.

## Checks
- DRC (KiCad 10.0.3, zones refilled): 0 copper errors, 0 unconnected; remaining
  68 items (silk / footprint library / courtyard) are identical to the original board.
- Pad-net diff vs original: only the 9 pads above changed.

## Not included
`gerbers/`, `fab_NCAB_20261004/` and the zips from the original folder are the
SPI3 version and were left out — regenerate the fab package from this board.

## Firmware
SPI2 for SYS_SPI (PB12 NSS, PB13 SCK, PB14 MISO, PB15 MOSI), FIN_HALL on PB11;
PC10/PC11/PC12/PA15 free. Bootloader over SPI2: slave, mode 0, ≤ 8 MHz (AN2606).
