# `spacer_battery_6` — fab callout

Companion to `K_spacer_cam.step` (3D geometry).

## Material

- **FR4** PCB interposer (same laminate family as the rigid tiles)
- thickness: 3.50 mm
- outline: Ø 34.0 mm disc

## Surface finish

- **ENIG (electroless nickel / immersion gold)** — solderable + flat (the spacer reflows to the tiles above and below)
- green LPSM solder mask both faces; lands left exposed

**Why FR4, not anodised Al:** the spacer is a routable PCB interposer — copper LGA lands on both faces joined by filled through-vias carry the power/GND/CAN backbone straight through on the same net, and it is reflow-soldered to the rigid tiles above and below. An anodised-aluminium disc can do neither (no plated vias, oxide won't take solder); the CNC-Al spacer was abandoned when the snake-flex interconnect proved infeasible. Per-board structural support is now carried by copper-coin inserts in the rigid tiles, not the spacer.

## Tolerances

- overall thickness: ± 0.05 mm
- routed outline / cavity edge: ± 0.1 mm

## Features

- 60 filled through-via(s) (60 capped + plated over for co-planar lands)
- 1 NPTH potting hole(s), Ø 3.0 mm each
- 1 top-face routed cavity(ies), depth 2.0 mm
- 0 bottom-face routed cavity(ies), depth 1.0 mm
- cavity / cutout geometry per the STEP + Gerber/drill set

## Notes

- All routing + drill from the STEP / fab data. No flat 2D drawing needed.
- Via fill must be capped and plated over (not just plugged) so the LGA lands seat co-planar — the backbone + cell rails rely on the fill being flush with the land.
- A through-cut cavity (battery compartment) is a routed window, not a blind pocket — cells nest into the aligned column of cuts.
