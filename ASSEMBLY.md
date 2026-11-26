# Smash tower — assembly instructions (PCBA → tower)

Maintained by hand in the repo root (`ASSEMBLY.md`); `export_production.py`
copies it into every `Manufacturing/<date>/` package with the export date and
commit, converts it to PDF, and appends the generated tables (Appendix):
per-tile part counts, underfill list, buffer-coat list, DNP list.

Items marked **(proposed)** are our proposal — please confirm or counter-propose
in your quotation.

## 1. Product and package

- **Product:** a potted electronics "tower": up to 6 round PCBAs (Ø34 mm,
  8-layer 2+4+2 HDI, 0.868 mm) stacked with spacer rings around a 3-cell
  primary battery, inside a laser-direct-structured (LDS) PEEK sleeve that
  carries the board-to-board wiring, vacuum-potted, closed by a nose cap and
  an aft cap.
- **PCBA deliverable:** one board design (264 × 102 mm) carrying the 8 tower
  boards (tiles) + the development toolkit (programmer strip, debug section),
  built two ways (§3.1):
  - **dev board:** everything fitted, no tile cuts;
  - **production board:** the tile cuts applied, the development toolkit DNP —
    only the 8 tiles fitted; the toolkit area is scrap after depanelling.
- **Configurations:** each tower uses the 5 core tiles + one nose
  payload tile (radar, QPD or camera). The package has `Common/` + one folder per nose
  (`radar/`, `laser/`, `camera/`), each with its own `README.pdf`.
- **Package contents:** see the top-level `README.pdf` (index against your
  data-exchange form).

## 2. Applicable standards and approvals (proposed)

| Topic | Standard |
|---|---|
| Bare board | IPC-6012 Class 3 (HDI: IPC-6012 + IPC-2226), IPC-4552 (ENIG) |
| Assembly workmanship | IPC-A-610 Class 3, J-STD-001 Class 3 |
| BGA / CSP | IPC-7095 (void limits Class 3), 100 % X-ray |
| Moisture-sensitive parts | J-STD-033 (handling, bake), J-STD-020 |
| Rework | **None.** A tile that fails inspection or test is scrapped, not reworked or repaired (no IPC-7711/7721 rework). Report each scrapped tile with its serial number and the failure. |
| ESD | ANSI/ESD S20.20 (or IEC 61340-5-1) |
| Materials | RoHS (EU 2011/65/EU + 2015/863): lead-free throughout |
| Approvals | No UL / CSA / ATEX listing required at PCBA level |
| Tower-level solder joints (sleeve via fills, aft-cap lane bridges, cell leads) | J-STD-001 / IPC-A-610 Class 3, like the PCBA |
| Cell pre-wiring (AWG 30 PTFE wire on the cell's + pin) | IPC/WHMA-A-620 Class 3 |
| Parylene coat | IPC-CC-830; coating criteria of IPC-A-610 Class 3 (thickness, coverage, masking) |
| Potting | No IPC class: void-free (verified by the optional lot audit CT, §6.2), fill level as specified |

## 3. Special requirements (PCBA)

### 3.1 What to populate
- **Dev board:** populate everything (BOM `Smash_BOM_dev_board.xlsx`, P&P
  `smash_panel_dev_board_*`).
- **Production board:** populate the 8 tower tiles only (5 core + radar, QPD,
  camera); the programmer strip and the debug section are **DNP** (flagged DNP
  in its pick-and-place data and listed in the DNP sheet of
  `Smash_BOM_common.xlsx`).
- Parts that are DNP by design inside the tiles (alternate footprints, e.g. the
  quartz TCXO footprint next to the fitted MEMS one) are also in the DNP sheet.
- **Do not substitute any part** outside the AML. Timing parts are MEMS on
  purpose (mechanical shock): quartz substitutes are not acceptable.

### 3.2 Solder and process materials (see `Common/Smash_materials.xlsx`)
- Reflow paste: **SAC305** (Sn96.5Ag3.0Cu0.5), both sides.
- **No conformal coating** — the boards are potted later. Flux residues must
  not impair the adhesion of the potting (Stycast 1090 SI): use a no-clean flux
  that you can show is potting-compatible, or clean to J-STD-001 Class 3
  cleanliness (ionic contamination < 1.56 µg/cm² NaCl eq.).
- **Underfill** (after X-ray, before depanelling) every BGA / CSP / WLCSP
  listed in Appendix B with the underfill named there: Henkel Loctite Eccobond
  **UF1173** (cure 5 min at 150 °C) or Henkel/Hysol **FP4549** capillary underfill.
- **Silicone buffer coat (required)** over the MEMS sensors and MEMS
  oscillators (the parts marked BUFFER in the BOM notes) and the 0402
  multilayer RF inductors of the S4 transverter (L_XV_PA_IN, L_XV_LNA_BIAS,
  L_XV_PA_VDD1 — Murata cautions against resin cure stress on its chip
  inductors): thin dome 0.2-0.5 mm of Dow SYLGARD 527, fully cured before
  the tower is potted, so the potting's cure shrinkage and expansion do not
  load them; never on castellations, the board edge or in the aft board's
  piezo pocket.

### 3.3 Mechanical / board handling
- The tile edges carry **castellated half-holes** (sleeve contacts): Ø0.50 mm
  plated holes in Ø0.70 mm pads at 0.80 mm pitch, 0.30 mm between holes
  (PCBWay normal process: hole ≥ 0.5 mm, edge-to-edge ≥ 0.3 mm). No burrs,
  no solder on the castellations, no paste or flux on the board edge. The
  castellations' copper annulus on both faces is **tented** (covered by solder
  mask) on production tiles: the electrically insulated (anodised or parylene)
  Al spacer rings bear on it, and the sleeve joint is soldered from the side
  into the plated half-barrel only.
- **Depanelling:** router or saw — **no hand snapping** (MLCC cracking). Sand
  the tab stubs flush with the Ø34.0 mm outline: the sleeve clearance is only
  0.1 mm.
- The **alignment notch** at the rim of every tile (1.2 × 1.0 mm, for the
  sleeve's rib) and the Ø3.0 mm potting hole (for the fixture pin) are datum
  features (§5.2): keep them free of burrs, solder and adhesive.
- Labelling **(proposed):** no labels on the tiles (no room, they are potted).
  Panel-level 2D code on the programmer strip; the inspection record of each
  tile is kept against that panel code.

## 4. PCBA assembly sequence (panel level)

1. Bake moisture-sensitive parts per J-STD-033.
2. SMT both sides, SAC305 reflow, lighter side first. During the second
   reflow the first side's joints remelt upside down: glue (SMT adhesive) any
   part on that side whose mass exceeds ≈ 30 g per in² of its pad area before
   the second pass.
3. 100 % AOI of both sides after the second reflow (the first side included:
   every part still in place); **100 % X-ray** of every BGA / CSP / LGA in the
   Appendix.
4. Underfill (§3.2), cure.
5. PCBA test (§6.1) while the tiles are still on the panel.
6. Production board only: depanel (§3.3), deburr, clean if required.
7. Per-tile finishing:
   - **camera_module:** bond the 0.5 mm aluminium heat spreader with a
     thermally conductive epoxy (proposed: Master Bond EP30AN-1).
   - **aft_end_board:** attach the Ø10 × 0.5 mm piezo disc (PI Ceramic
     PIC181, wrap-around contact) with **In52/Sn48** (liquidus 118 °C) — the last solder step
     on that board; it sits in the battery floor plate's pocket.
   - silicone buffer coat (§3.2).
8. Pack per tile in ESD packaging, with the test record.

## 5. Tower assembly (if quoted: after the PCBA)

### 5.1 Parts per tower
Common parts: `Common/Smash_materials.xlsx` (sheets *Mechanical parts*,
*Purchased mechanical*), STEP in `Common/STEP/`. Nose-specific parts:
`<nose>/Smash_mechanics_<nose>.xlsx`, STEP in `<nose>/STEP/`.

### 5.2 Alignment: sleeve rib + fixture pin (nose down)
- The tower is stacked **nose down, inside its sleeve**, on a fixture that
  holds the sleeve (nose end down) and carries **one Ø2.9 mm pin** standing
  up at the potting-hole position (r 13.0 mm from the centre, 135°).
- **Rotation — the sleeve's rib:** a 1.0 mm axial rib inside the sleeve at
  285° engages the 1.2 × 1.0 mm rim notch of every board, the 1.2 mm gap of
  every spacer ring, the battery holder's axial groove and the floor plate's
  notch. Every part is keyed as it drops in; the ring gap also fixes the
  ring's orientation.
- **Centring — the pin:** it runs up the Ø3.0 mm potting holes of every board
  and the battery holder's potting channel; the sleeve's bore (Ø34.2 over the
  Ø34.0 boards) does the rest.
- The fixture also locates the sleeve (its nose end and the rib), so the
  sleeve's vias sit at **fixed nominal positions** relative to the pin and
  the rib (the sleeve's unrolled KiCad layout and copper STEP give them): one
  drill / solder program per configuration.
- Angles are in the tower frame (aft_end_board top view, 0° = +X, counter-
  clockwise); the fixture design is yours — the STEPs give the features.

### 5.2a Nose insert on the payload tile (before stacking)
The payload tile carries a nose insert that keeps the potting off its front:
- **Radar:** the **AoP dam**, a 1.5 mm tall rectangular collar round the
  AWR1843's antenna-on-package (`aop_dam.step`), natural (unfilled) PEEK, low
  loss at 77 GHz. The space inside stays air; the radome is in the nose cap.
  An arm joins it to an **anchor ring round the radar tile's potting hole**
  (C-shaped, open toward the sleeve so the potting coming up through the hole
  flows out sideways); the arm's underside is relieved to bridge the parts in
  between.
- **Laser / camera:** the **optic insert**, the light tube over the sensor
  (`optic_insert.step`). Black PEEK (opaque). The light path inside stays air.

Bond it on the PCBA (no cells yet, so the adhesive's normal cure applies):
plasma-clean both faces, a **closed bead** of Loctite EA 9466 round the
collar's footprint, then place the insert on a bonding jig with a Ø2.9 pin
through the anchor ring and the tile's potting hole: the pin sets the
position, the package (0.6 mm clearance) the rotation. Cure. The bead must be continuous: it is what keeps the potting
out. Inspect it before stacking.

### 5.3 Sequence (proposed)
1. **Sleeve** (per configuration, LDS lanes and via pads already plated, no
   holes yet) into the fixture, nose end down, over the pin.
2. Drop in, each part on the rib and over the pin: payload tile (radar / QPD /
   camera, its nose insert bonded on; the fixture base carries a platform
   that sets the tile 2.75 mm below the sleeve's nose rim, and the pin runs
   through the dam's anchor ring) → 7075 ring → companion_compute → 7075 ring → power_board → PEEK
   GF30 ring → wakeup_board → PEEK GF30 ring → activation_interface → battery
   holder (7075-T6).
3. **Cells:** 3 × Tadiran TLM-1520HPM/P, pre-wired (+ pin trimmed, AWG 30 wire
   soldered flat), into the holder bores from the open aft end (on top).
   **From here on the cells are live and nothing may exceed 85 °C.**
4. **Floor plate**, then **aft_end_board** (piezo attached; − pins and + wires
   through its PTHs). **Before soldering**, check each cell: + wire to its − pin
   reads +3.6 V (a reversed cell puts BAT_RAW at −3.6 V, below the LDOs'
   −0.3 V limit, and the other two cells drive it through 2 × 0.2 Ω). Solder
   the cell leads on its aft face (on top) with In52/Sn48 (low-temperature
   iron, heat-sinked leads), then check BAT_RAW (R_BAT*_ISO) reads 3.6 V.
5. **Aft cap** (hard-anodised 7075 disc with the PEEK-LDS crown overmoulded
   on its rim; the disc backs aft_end over its whole face and its access
   holes sit over the clamp tabs and centre pads): 3 × M2 × 6 ISO 14580 A2-70
   low-head screws clamp cap → aft_end → floor plate into the holder's M2 taps.
   **ESD control while fitting the nichrome restraint wires** (wrist strap,
   ionizer, grounded tools): the clamp tabs reach the cutter's column FETs
   (40 V), and their 36 V TVSs only clamp to ≈ 58-80 V on a strike.
6. **Sleeve vias, still on the fixture:**
    - Laser-drill each via (CO2 laser, Ø0.3-0.4 mm) through the centre of its
      LDS pad and the sleeve wall; the CO2 laser stops on the castellation
      copper. (proposed sleeve pattern: each via pad is a copper ring with an
      open centre, elongated axially to absorb the stack-height tolerance of
      the rings and boards — added to the sleeve layout.)
    - Clean the laser residue off the castellation copper (your process), fill
      with Sn42Bi58 (138 °C) by solder-jet or laser soldering: the solder joins
      the castellation copper to the pad ring.
    - Bridge each aft-cap lane to its sleeve lane across the cap / sleeve
      joint with Sn42Bi58.
7. **Continuity of every lane** (§6.2).
8. Lift the tower off the fixture (the pin comes out) and turn it **nose up**.
9. **Potting:** plug the IR light pipes; the AoP dam (radar) or the optic
   insert (laser / camera) keeps the potting off the payload's front, the space
   inside it stays air. Feed from the top down the
   potting channel (the boards' Ø3 holes) to the aft end, so the potting fills
   from the bottom up; the sleeve's inner grooves at 105° / 285° vent to the
   top. Stop when the potting comes up through the payload tile's potting hole
   and spreads ≈ 0.5 mm over the payload tile (the nose cap is not potted).
   **Henkel Loctite Stycast 1090 SI + Catalyst 23LV** (low-density syntactic
   epoxy, chosen for its low RF loss and low mass): vacuum degas, then cure
   4–6 h at 45 °C (or 16–24 h at 25 °C) — **≤ 85 °C** (cells). It is filled
   with hollow glass microspheres: confirm the vacuum / pressure limits with
   Henkel before any pressure cure, and qualify the fill of the 0.1 mm
   board-edge gap on the first articles.
10. **Nose cap:** press the Ø40 cap over the sleeve neck (0.06 mm radial
    interference) — permanent.
    - (optional) Before pressing, apply a structural adhesive to the neck
      (e.g. Loctite EA 9466 epoxy); for the best bond to PEEK, plasma-activate
      the neck and the cap bore first.
11. (proposed) **Outer coat:** parylene C, 15–25 µm, vapour-deposited at room
    temperature over the whole tower (sleeve, via fills, aft cap, nose cap and
    their joints — it seals the nose-cap joint). Mask only the aft cap's
    contact crown. It also insulates the sleeve lanes; at this thickness it has
    no measurable effect on the antennas.

12. **Bench validation** on the test fixture (the programmer board's aft
    fixture): seat the tower aft cap down — guide collar over the sleeve, the
    aft cap's 3 locating holes on the fixture dowels, its crown contacts on the
    spring pins — and hold it down by hand; the three SEAT LEDs lit = seated
    flat. The programmer powers the tower through the EXT POWER contact
    (≈ 5.6 V, metered) and runs the electronics validation per our test
    specification and firmware (§6.2).

The six major steps, one page each with drawings, are in each nose folder's
`Assembly_steps.pdf`: 1 assembly (steps 1–5), 2 vias and copper (6–7),
3 potting (8–9), 4 nose cap (10), 5 parylene coat (11), 6 bench validation (12).

## 6. Test requirements (what to test)

### 6.1 PCBA (per tile)
- AOI 100 %, X-ray 100 % of BGA / CSP / LGA parts (IPC-7095 Class 3 voids).
- No shorts between supply rails and GND (all rails of the tile), e.g. by
  flying probe against the netlist.
- No programming and no functional test: the devices are delivered blank.
- Inspection record per panel code.

### 6.2 Tower
- The tiles are only connected once the sleeve vias are filled, so every tile
  must pass §6.1 before it goes into a tower.
- After the via fill: continuity of every sleeve lane (aft cap contact →
  castellation, against the netlist).
- (optional) **Lot audit** on sample towers of each lot: a **CT scan** (void-free
  potting, via fills wetted on the castellation copper and the pad ring) and
  the **bench test**, both before and after the shock test, compared per serial
  number (delta: cracks, voids, joint or part movement, electrical drift).
- Final: bench validation of the electronics on the test fixture (step 12),
  per our test specification; result recorded per tower serial number.
