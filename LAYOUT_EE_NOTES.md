# Layout EE notes

Maintained by hand in the repo root (`LAYOUT_EE_NOTES.md`); `export_unrouted.py`
copies it into every `Unrouted/<date>/` export with the export date and commit.
Footprint provenance (what to check before fab) is in **FOOTPRINT_REVIEW.md**
next to this file, generated from the design at export time.

## 0. Before you start — open design decisions

- **Nose USB-C (usb_nose, J_USB_C)** will change from the Same Sky UJ20
  (China origin) to **Hirose CX80B2-24P** (vertical, 24-pin, ~6.5 mm) once the
  Hirose drawing is in. Route the USB nose last / keep the connector area flexible.
- RF matching values on the S4 transverter (LO pad, PA supply choke, LNA match,
  4.4-5.0 GHz BPF + L-match) and the LR2021 HF match are **placeholders**: lay
  out the topology with 0402 pads; values come from bench tuning.

## 1. What is in this package

- `Smash.kicad_pro / .kicad_sch / .kicad_pcb` — the whole tower as one KiCad
  project: every board is a tile on one panel ("twin" of the stack). Open this.
- `footprints/`, `stackup.kicad_sym`, `3dmodels/`, `datasheets/` — project-local
  libraries (`${KIPRJMOD}` paths), so the folder is self-contained.
- `step/` — every board STEP (+ `_layered`), the spacer rings with their
  `_cam.md` (material / finish), battery holder + floor plate, sleeve, potting
  mould, and the full component stack (`stackup_components.step.zip`, zipped
  for GitHub's 100 MB limit).
- `FOOTPRINT_REVIEW.md` — footprint provenance list (see §4).
- `dev_board/` — the **dev board** KiCad project (`dev_board.kicad_pro`): the
  whole tower schematic on one flat 285 × 102 mm 8-layer board + the USB
  diagnostic section; its footprints, `fab/` (dev + production gerbers),
  `PANEL_NOTES.md`, the fixture collar STEP and its own `3dmodels/`. Its datasheet
  links point at the shared `../datasheets` (keep the folder structure when copying).
- The same folder is also next to it as `<date>.zip`.

### Importing into Altium (3D models)

Altium imports the KiCad files with **File » Import Wizard » KiCad Design
Files**, but its KiCad importer **does not bring footprint 3D models along** (two
dev-board imports, `${KIPRJMOD}` and plain relative paths: no models, and the
import log never mentions them). Add them with the script in this package:

1. Import the project, open the imported PcbDoc and **Design » Make PCB Library**.
2. With that PcbLib active: **File » Run Script… » `Attach3DModels.pas` »
   `RunAttach3DModels`** (the .pas is next to each project: export root for the
   tower, `dev_board/` for the dev board).
3. Pick that project's **`3D_MODEL_MAP_altium.txt`** — footprint → STEP in
   `3dmodels/` + KiCad's offset and rotation. The script embeds each STEP as a
   3D body (skips footprints that already have one) and reports attached /
   missing / unmatched (details in `Attach3DModels_log.txt`).
4. Save the PcbLib, then **Tools » Update PCB With All**.

⚠ First run is the test: check a few parts in 3D (key 3). If parts lie on their
side or upside down, flip `ROT_SIGN` at the top of the script (KiCad stores
model rotations with negated angles; the script assumes that), delete the added
bodies and run again. Footprints rotated about two axes are listed in the
summary — check those. Footprints with no STEP never had a vendor model
(FOOTPRINT_REVIEW.md); `3D_MODEL_MAP.csv` has the same data for manual
**Place » 3D Body**.

Stack (bottom → top): A aft_end_board · B-G battery spacers · H
activation_interface · I spacer · J wakeup_board · K spacer · L power_board ·
M spacer · N companion_compute · O spacer · P radar_module (or camera / QPD /
USB nose). Tiles are Ø34, 8-layer 2+4+2 HDI, 0.868 mm. Stack 39.2 mm (core /
radar / QPD), 39.7 mm with the camera nose.

## 2. Conventions (information, not enforced)

- **Antenna keep-outs are SILKSCREEN** ("ANT … KEEPOUT: NO COPPER r > …, all
  layers") on the boards next to the sleeve slot antennas — not copper
  keep-out zones. Please honour them in copper on every layer.
- **Spacer cut-outs are drawn on the silkscreen** of both neighbouring tiles
  (fold-mirrored). Keep face parts inside the drawn window and the spacer needs
  no re-mill. Gap heights are set by the tallest part pair across each gap.
- **Pre-routed copper is a starting point**: castellation escape stubs, the LDS
  sleeve bus (radial stubs → r 19.6), and the activation_interface reference
  routing (an imported reference layout). ⚠ That reference routing came
  from Freerouting with ONE rule (100 µm / 75 µm, 0.45/0.20 via) — all nets at
  4 mil including ACTIVATE_HV (33 V) and BAT_RAW: **re-derive power widths per
  net class before fab.**
- **Locked placements** (`application/src/smash/data/locked_placements.json`,
  each with a reason) are mechanical/thermal/RF constraints — talk to us before
  moving them. Notably: the launch piezo cluster on aft_end top (sits in the
  floor plate's underside pocket), the cell − pin PTHs and + wire pads
  (P_CELL_PIN_NEG1-3, P_CELL_WIRE_POS1-3, under the bore grooves), radar AoP,
  MP25 reference placement on companion_compute.
- **Assembly datums:** every board has a 1.2 × 1.0 mm **rim notch at 285°**
  (Edge.Cuts; the sleeve's internal rib keys it) and the Ø3.0 potting hole at
  135°, r 13 (the assembly fixture's pin runs through it) — keep copper, parts
  and silk clear of the notch, and don't move either feature.
- **Missing 3D models** are deliberately not faked (see FOOTPRINT_REVIEW.md):
  please pull them from the vendor site where needed.
- The aft_end **health-coil spiral** (In2.Cu / In3.Cu, r 13-15.5 mm) is
  generated copper added after placement — keep it, route around it.
- **DDR3L** (MT41K256M16TW, companion_compute): A/C + data mapping is ST's AL
  10×10 DDR3L template verbatim; route with ST's length template (CLK ±3.55 mm
  A/C window, DQS ±1.42 mm) — `Research/STM32MP25xxAx/STM32MP25xxAL/`.

## 3. Board-specific notes

- **Debug castellations (radar_module, wakeup_board, companion_compute)**:
  board-local debug nets on castellation pads of their own board, numbered
  after the lane pads. No sleeve lane faces them (open in the tower); on the
  dev board each one's escape stub ends on a Ø2 test point (TP_DEV_DBG_<net>).
  Route each as a plain trace from the pin to its pad; short stubs are fine.

  | Board | Net | From (pin) | Sleeve angle |
  |---|---|---|---|
  | radar_module | AWR_TCK | U_AWR T3 | 230.1° |
  | radar_module | AWR_TMS | U_AWR U8 | 254.4° |
  | radar_module | AWR_TDI | U_AWR U9 | 211.1° |
  | radar_module | AWR_SOP0 (= TDO) | U_AWR U10 | 224.7° |
  | radar_module | AWR_DBG_GPIO | U_AWR M2 (GPIO_0) | 240.9° |
  | wakeup_board | LR_SPI_SCK | U_WBA H8 | 111.0° |
  | wakeup_board | LR_SPI_MOSI | U_WBA G8 | 116.4° |
  | wakeup_board | LR_SPI_MISO | U_WBA G7 / U_LR | 257.1° |
  | wakeup_board | LR_NSS | U_WBA G1 | 132.6° |
  | wakeup_board | LR_BUSY | U_WBA D7 | 140.8° |
  | wakeup_board | LR_IRQ | U_WBA B2 | 151.6° |
  | wakeup_board | XV_LO_MUX | U_WBA D2 / U_XV_LO 30 | 165.1° |
  | companion_compute | PMIC_NRST | U_PMIC 31 | 230.1° |
  | companion_compute | PMIC_WAKEUP | U_PMIC 30 | 254.4° |

- **wakeup_board — antenna matches**: S1 (shared BLE / LR2021) has a fixed
  match between the owner switch U_ANTSW_S1 and the ANT_HF_S1 castellation:
  C_ANT_S1_DCBLK 0.8 pF in series right at the castellation, C_ANT_S1_SHUNT
  0.5 pF to GND on the switch side. S4: C_ANT_S4_MATCH 0.8 pF in series at
  the ANT_HF_S4 castellation. All C0G 0402; keep them on the feed line with
  short GND vias (sub-pF values: pad parasitics matter).
- **power_board — LTC3124 (U_COMP_BOOST)**: 2-phase boost; keep both phase loops
  (SWA/L_BOOST_COMP, SWB/L_BOOST_COMP_B) symmetric and tight, VOUTA/VOUTB and
  PGNDA/PGNDB joined at the part; pin 14 (NC) tied to VOUT for copper. The
  SnapMagic land has **no paste on the exposed pad — add paste windows**.
- **radar_module — TPS62822 / TPS62088 bucks**: L_AWR_BUCK13 is 0.24 µH, Isat
  4.6 A vs the TPS62088's 5.0 A max switch limit — check at bring-up; small
  hot loops, CFF (120 pF) right at FB.
- **camera_module — VB1943 (OBGA-74, 0.8 mm)**: own 1.15 V core buck
  (U_CAM_BUCK_VCORE, TPS62822). Per DS Table 7: 470 nF on VCORE and 100 nF on
  VANA at the balls; CPNEG (10 µF), CPPOS (1 µF), VRT (2 × 2.2 µF) and LDO2V4
  (470 nF) caps close to their balls, AGND side. 2-lane MIPI CSI-2 (DATA1/2 +
  CLK) as 100 Ω differential pairs; lane order/polarity can be remapped in the
  sensor, so swap pairs if it routes better (tell firmware). Sensor is 2.2 mm.
- **aft_end_board — piezo pocket**: everything in the pocket (piezo disc,
  U_COMP_PZ MAX9064 + 0402s, D_ACT_WIRE diodes) sits under the 1.2 mm 7075 floor
  plate: 0.6 mm pocket, and a 1.8 mm-square **0.9 mm sub-pocket only over
  U_COMP_PZ at (7.8, 0)** (the UCSP is 0.69 mm). Moving U_COMP_PZ means
  re-milling the plate (spacer_step.BATT_PZ_COMP_POCKET_MM). The 0402s clear the
  plate by only 0.10-0.15 mm. PIEZO_P is a high-impedance charge node: keep it
  microscopically short. The disc is attached LAST (In52/Sn48 118 °C).
- **wakeup_board — BAT_SENSE** (R_BAT_SENSE_H/L 1 M / 1 M + 100 nF → WBA PA3):
  high-impedance; cap at the WBA pin, keep the node short and away from SW nodes.
- **wakeup_board — LoRa TCXO dual footprint**: Y_LR_TCXO_MEMS (SiT5356) is
  fitted; the quartz Y_LR_TCXO (TG2016) footprint is unfitted (shock rule) —
  keep both, overlapping as drawn.

## 4. Footprints to check (summary — full list in FOOTPRINT_REVIEW.md)

- **Self-drawn from datasheets / project scripts** (never built): MCP1640 DFN-8
  (U_BOOST, U_XV_BOOST), ABLIC HSNT-4 (S-1318, U_AON_LDO / U_TMR_LDO), Infineon
  TSLP-2-1 (BAS40-02L, D_ACT_WIRE_*), VSMB1940X01 0805 IR emitter, GRF5126 QFN16
  / GRF2073W DFN8, MT03-092 QPD (TO-8), piezo disc, cell lead PTHs (Ø0.8 pin is
  a placeholder until Tadiran confirms), clamp tabs, pogo pads.
- **Vendor lands we changed**: 3D models rotated by us (LTC3124, VB1943,
  BUK6D120, S-1318, GRF5126, GRF2073W, H3LIS331 — check pin 1 in the 3D
  viewer against the land's pin 1), and lands taken
  from a sibling part or named after one (STM32MP255F land for the MP257F,
  LTC5549 land for the LTC5552, PE64904C for D, SST26 SON-8 for the MX25V8035F,
  SiT5356 20 MHz for 32 MHz, DSC1001 family, H3LIS331 on a LIS3DH LGA-16 land,
  SSM3K35 on SSM3J64, SSM3K7002 on 1SS294, BLM18PG on BLM18SP).

## 5. Dev board (`dev_board/` in this package)

- Programmer strip: USB-C (CC1/CC2 5.1 k to GND at the connector) → ESD →
  probe MCU U_DEV_MCU (USB FS on PA12/PA11, no hub). J_DEV_LA = logic-analyzer
  header (20 inter-tile bus signals on odd pins, GND on even pins).
  S_DEV_MP25_BOOT / probe PB13 pull the MP25 BOOT0/BOOT2 net low (UART/USB
  serial boot; the tower's 10 k pull-up selects serial-NAND boot) through
  U_DEV_BUSSW3 / U_DEV_FLATSW3.
- Debug test points TP_DEV_DBG_* sit just outside the tiles at the end of
  their castellation's escape stub (pre-routed on F.Cu); keep them clear.
- J_DEV_HF_S1 / J_DEV_HF_S4 (u.FL) are on the slot side of the feed matches:
  conducted S1 levels read ≈ 3.3 dB low at 2.44 GHz, S4 ≈ 0.7 dB.
- J_DEV_USB is still the Same Sky UJ20-C-H (China origin); 4 annular-ring DRC
  errors on its shell slots. It is due to become the Hirose CX90B-16P (accepted,
  not applied yet: the SnapMagic land is the CX90B-16P1 file and needs checking
  against Hirose's drawing) — leave room around it.
- P_DEV_FIX pogo pads: 4 courtyard overlaps (tight fixture pitch) — confirm.
- ERC "power pin not driven" on 3V3 / GND = missing power flags only.

## 6. Known DRC state

- Configuration panels (generator run 2026-11-23): core_radar, core_qpd and
  core_camera clean; core has 2 annular-width errors. Dev board: the items in §5.
- The combined `Smash.kicad_pcb` panel shows 188 errors (163 copper-to-edge,
  mostly the castellation escape stubs; 15 zone overlaps; 8 clearance; 2
  annular). Most are artefacts of showing every tile on one
  panel, but they have not been triaged one by one — run DRC per board as you go.
