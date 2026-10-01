# Component-catalog gaps

Open items per part. Use this to (a) prioritise the next round of
artifact pulls and (b) flag design-intent corrections that need to land
in the schematics when we rebuild from this catalog.

The principle: **factories only encode data we have ground-truth for.**
Everything missing or wrong is recorded here, not invented.

---

## 1. Design-intent corrections (hallucinated PNs to fix when rebuilding the schematic)

These are part numbers referenced in the project that turn out to be
invalid or wrong on careful datasheet review. Fix the schematic refs
to use a real PN when porting the design to use this catalog.

| referenced PN | status | datasheet-correct alternatives | notes |
|---|---|---|---|
| `STLQ020M33R` | RESOLVED — `STLQ020C33R` recommended | `add_stlq020c33r` (SOT323-5L, leaded — best match for original SOT-23-5 intent) **or** `add_stlq020j33r` (DSBGA-4, smaller but needs underfill) | Original system.py used `AP2112K-3.3` SOT-23-5 placeholder with `manf_pn="STLQ020M33R"` (hallucinated). STLQ020 doesn't ship in SOT-23-5; closest variant is **C33R (SOT323-5L)** — 5-lead leaded, shock-tolerant for 1000+ G launch. Alternative `J33R` (DSBGA-4) is smaller but Flip-Chip → underfill required. Both factories shipped; recommend **C33R** for the WLE5 always-on LDO position on wakeup_board. |
| `DSC1001CI5-032.7680` | RESOLVED — replaced with `SiT1630AE-S6-DCC-32.768E` | Factory `add_sit1630ae_s6_dcc_32_768e` shipped. | DSC1001/3/4 family datasheet (Microchip) explicitly states **frequency range 1 MHz to 150 MHz**, so the original PN was hallucinated. Replacement is SiTime SiT1630 — 32.768 kHz MEMS osc, SOT23-5, 1.0 µA, ±20 ppm. **Sourcing flag**: SiTime's analog ASIC uses TSMC Taiwan — verify against Smash's TW exclusion before fab lock-in. If TSMC dependency is unacceptable, swap to Microchip DSC2311 / DSC6101 (USA-fab). |
| `AWR2944ALBGALTRQ1` | **wrong variant** — Smash needs the full AWR2944, not LC | `AWR2944ABGALTRQ1` (full AWR2944, 4 MB + DSP + Aurora + Ethernet + CSI2 RX, T&R packing) | The design's earlier BOM reference (`ALBGALTRQ1`) was the LC variant which drops DSP, Aurora LVDS, Ethernet, and CSI2 RX. Smash needs the full feature set for firmware-headroom reasons. Use `add_awr2944abgaltrq1` (tape & reel) in the rebuild. The LC factory `add_awr2944albgaltrq1` is kept in the catalog for reference only. |

Add rows here when more come to light during the system.py audit.

---

## 2. Existing factories — per-part field gaps

Fields below are `None` (not invented) because the datasheet doesn't
state them. Fill these by pulling the linked source.

### `add_irlml6402trpbf` (Infineon IRLML6402TRPBF)
| field | gap | source to pull |
|---|---|---|
| `fab_country` | unknown | Infineon Mouser product page → "Country of Origin", or Infineon traceability PDF |
| `currency`, `price_1pc`, `price_20kpc` | unknown | live Mouser quote: 942-IRLML6402TRPBF |
| `weight_g` | unknown | Infineon package drawing (SOT-23 ≈ 0.008 g typical, not datasheet-stated) |
| `body_material`, `lead_material` | unknown | Infineon material declaration form (request via FAE) |
| `rth_jc_cw` | not in datasheet | datasheet only gives R_θJA |
| Footprint courtyard verified against SOT-23 IPC density-B | OK |  |

Qualification flag: **Consumer-grade (JEDEC JESD47F)**. Surface to
sourcing if Smash is shipped as a mil-aero product — may need a more
qualified P-FET equivalent.

### `add_irlml6244trpbf` (Infineon IRLML6244TRPBF)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | Mouser 942-IRLML6244TRPBF + Infineon material decl |
| `rth_jc_cw` | not in datasheet |  |

Same Consumer-grade caveat as IRLML6402.

### `add_bss138lt1g` (onsemi BSS138LT1G)
| field | gap | source to pull |
|---|---|---|
| **SamacSys ZIP / `.kicad_mod`** | **MISSING from repo** | fetch via SamacSys ECAD model loader (KiCad LibLoader) using onsemi PN BSS138LT1G. Footprint currently built from datasheet p6 recommended mounting footprint (0.56 × 0.95 mm pads) — replace with SamacSys-generated when available so it matches the project's footprint convention. |
| `fab_country`, pricing, weight, materials | unknown | Mouser 863-BSS138LT1G + onsemi material decl |
| `rth_jc_cw` | not in datasheet |  |

For automotive/high-reliability paths, **switch to `BVSS138LT1G`** (same
die, AEC-Q101 qualified, PPAP capable). When this becomes relevant we'll
need a separate factory or a parameter on this one.

### `add_ldl112pv33r`, `add_ldl112pv18r` (STMicroelectronics LDL112 family)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | Mouser 511-LDL112PV33R / 511-LDL112PV18R |
| `standards` list | empty (RoHS/Pb not explicitly stated on this datasheet) | request ST compliance declaration; assume RoHS-Pb-free until proven otherwise |
| `eccn`, `itar` | unknown |  |

**Pin-3 convention discrepancy**: the SamacSys symbols disagree on the
fixed-version pin-3 label:
- LDL112PV33R: pin 3 = `ADJ`
- LDL112PV18R: pin 3 = `NC_1`

Both refer to the same physical pin; the datasheet (p3 Table 1) says it
is the `ADJ` pin and is "not connected on the fixed version." When
porting the schematic, **always tie this pin per datasheet** (leave
floating or to GND per ST's app-notes) — don't trust the SamacSys-generated
name.

### `add_stlq020j30r` (STMicroelectronics STLQ020J30R)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | Mouser 511-STLQ020J30R |
| `standards` | only ESD declared | request ST compliance for RoHS/Pb-Free |
| `rth_jc_cw` | not stated for Flip-Chip 4 in this datasheet | only DFN6-2x2 and SOT323-5L variants list R_thJC |

**This factory is 3.0 V (J30R).** If the design rail truly needs 3.3 V
(STLQ020M33R was the hallucinated reference), add a separate
`add_stlq020j33r` factory once we pull its SamacSys ZIP. The die is
the same — only the trim differs.

### `add_ltst_c190gkt` (Lite-On LTST-C190GKT green LED)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | Mouser 859-LTST-C190GKT |
| `rth_ja_cw`, `rth_jc_cw`, `tj_max_c` | not stated | Lite-On reliability spec sheet (request via FAE) |
| `vcc_nominal_v` | meaningless for an LED — leave None |  |

**Munition-zone applicability**: datasheet p9 explicitly disclaims
high-reliability use. If Smash is mil-aero, sourcing needs to qualify
Lite-On for this PN or substitute with a MIL-PRF-19500-style LED.

### `add_mcp1640ct_i_chy` (Microchip MCP1640CT-I/CHY)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | Mouser 579-MCP1640CT-I/CHY |
| `rth_jc_cw`, `rth_ja_cw` | not in datasheet headline | request Microchip thermal spec |

**Source-of-truth caveat**: `Research/MCP1640CT-5002H_CHY.pdf` —
the file name contains the trim suffix "5002H" which doesn't appear
in the datasheet body. May be a customer-coded preset trim. Verify
with Microchip whether the design needs `MCP1640CT-I/CHY` (standard)
or a custom `MCP1640CT-5002H/CHY` (if real).

**Variant note**: this factory is the C-variant (auto PFM/PWM with
input-to-output bypass in shutdown). If the design relies on the
disabled output going to high-Z (no bypass), switch to the A/B
variant — different shutdown behaviour, separate factory.

### `add_lmr10510xmfe_nopb` (TI LMR10510XMFE/NOPB)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `rth_jc_cw`, `rth_ja_cw` | not retrieved from datasheet thermal section | extract from §10.3 or pull supplementary thermal spec |

**Variants**: `LMR10510Y` (3 MHz, vs the X variant's 1.6 MHz) and the
6-pin WSON package are separate orderable parts — add separate
factories if needed.

### `add_tps61085pw` (TI TPS61085PW)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `rth_jc_cw`, `rth_ja_cw` | not retrieved from §7.4 | extract from datasheet thermal section |

**Variant note**: VSSOP-8 (DGK) is also covered by the datasheet but
needs its own factory (different footprint `SOP65P490X110-8N` is the
TSSOP version; VSSOP would be a different IPC name).

### `add_tps61175pwpr` (TI TPS61175PWPR)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `rth_ja_cw=45.2`, `rth_jc_cw=5.8` populated from datasheet §6.4 |  |  |

**Pin 11 (NC) caveat**: the datasheet explicitly says "Reserved pin.
Must connect this pin to ground" — captured in the Pin.note. Don't
silently treat as unconnected when porting the schematic.

### `add_mbrs340t3g` (onsemi MBRS340T3G)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing | unknown | live Mouser quote |
| `weight_g=0.217` populated FROM DATASHEET (p1 Mechanical Char) |  |  |
| `body_material="epoxy mold compound (UL 94 V-0)"` populated FROM DATASHEET |  |  |
| `lead_material` | "corrosion-resistant external surfaces" — vague | request onsemi material declaration |
| `rth_ja_cw` | not in datasheet (only R_θJL=11 °C/W is) |  |

**Variant for automotive**: switch to `SBRS8340T3G` (same die,
AEC-Q101 + PPAP). Separate factory when needed.

### `add_lmv331idbvr` (TI LMV331IDBVR)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `rth_ja_cw`, `rth_jc_cw` | datasheet §5.4 has the table but not extracted to schema | revisit |

**Output is open-drain** — schematic must always include an external
pull-up to the desired output rail. Captured in `Pin("OUT").note`.

**Family variants** `LMV393` (dual) and `LMV339` (quad) live in the
same datasheet (SLCS136V) — separate factories when needed.

### `add_tmp117maidrvr` (TI TMP117MAIDRVR)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `rth_ja_cw`, `rth_jc_cw` | not in datasheet headline | extract from §6.4 |

**ADD0 wiring**: the I²C address is selected by tying ADD0 to one of
GND / V+ / SDA / SCL (yielding 0x48..0x4B). When porting the
schematic, check what address the firmware expects and tie ADD0
accordingly.

**YBG (DSBGA) variant** is a separate factory if the design uses the
smaller-footprint package.

### `add_iis2mdctr` (ST IIS2MDCTR)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `tj_max_c` | not stated explicitly | request ST thermal spec |

**Pin 5 (C1) caveat**: external decoupling/tuning capacitor pin.
Verify per ST's app-note / reference design what value (typically
~100 nF X7R to GND).

**Sensitivity to mechanical shock** — datasheet p14 explicitly notes
this. May need shock-protection during Smash launch (1000+ G).

### `add_ism330dhcxtr` (ST ISM330DHCXTR)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `tj_max_c`, full ESD ratings | not extracted | revisit datasheet electrical section |

**ML Core / FSM** are real hardware features (datasheet p1, ST app
notes AN5392 and AN5388). When the design wants to use them, ST
provides Unico GUI to generate the configuration register sequence
that the firmware writes at boot. No additional pin connections —
runtime-only.

**Aux SPI (pins 2/3/10/11)** lets ISM330DHCX act as a sensor hub to
external slaves. If unused, ground per datasheet.

### `add_h3lis331dltr` (ST H3LIS331DLTR)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `tj_max_c`, full ESD ratings | not extracted | revisit datasheet |

**Reserved pins (10, 15) must be tied to GND** — datasheet
explicit. Pin notes encode this.

**Picked for shock survivability** (10000 g rated) — relevant to
Smash's launch loads. Surface in design-rationale documentation.

### `add_tcan1042gvdq1` (TI TCAN1042GVDQ1)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `rth_ja_cw`, `rth_jc_cw`, `power_rating_w` | not extracted | revisit §7.5-7.6 |

**Family selection sanity check**: TCAN1042 has 8 variants —
H/non-H × G/non-G × V/non-V. We have the GVDQ1 = 5 Mbps with VIO.
Confirm against the design's required bus speed (5 Mbps needs G) and
MCU I/O level (3.3 V on Smash → V needed unless MCU is 5 V tolerant).

**Routing rules**: CANH/CANL must be a 120 Ω differential pair,
terminated 120 Ω at both bus ends. STB pin must not float.

### `add_dsc1001ci5_008_0000` (Microchip DSC1001CI5-008.0000)
| field | gap | source to pull |
|---|---|---|
| `fab_country`, pricing, weight, materials | unknown | live Mouser quote |
| `voltage_rating_v` | not literally stated (Abs Max is V_DD+0.3) | refine when adding 32k variant |
| `vcc_nominal_v` | caller decides (1.8/2.5/3.3 V typical) |  |

**Order-code parsing**: `DSC1001 C I 5 -008.0000` decodes as
- DSC1001 = family (1-150 MHz CMOS MEMS osc)
- C = Industrial -40..+85 °C  (Microchip's order-code convention here)
- I = ±25 ppm
- 5 = CDFN/DFN 2.5×2.0 package
- 008.0000 = 8.000 MHz

Stability tolerance (±25 ppm) is stored as `tolerance_pct=0.0025`.

**Family-frequency caveat**: this family DOES NOT support 32.768 kHz
or any frequency below 1 MHz. Catalog has explicit hallucination
correction in §1 above.

---

## 3. Deferred factories (no artifacts in repo yet)

### `add_bat64_06` (Infineon BAT64-06 Schottky array, SOT-23, common anode)
- Datasheet: `Research/BAT64-06.pdf` (Infineon, 2014-02-11) — present.
- SamacSys ZIP: **MISSING**. The user expected one for BAT64-06W (the
  SOT-323 variant) but a scan of every archive in
  `downloads/{,processed/}` shows no BAT64 of any kind.
- KiCad symbol: **MISSING**.
- Footprint `.kicad_mod`: **MISSING**.
- STEP 3D model: **MISSING**.
- Pinmap.txt: **MISSING**.

**Source to pull:** SamacSys ECAD Model Loader using Infineon PN
`BAT64-06` (SOT-23) or `BAT64-06W` (SOT-323), whichever the design
actually uses. Confirm package choice on the schematic.

**Design-intent note:** BAT64-06 is the common-anode variant. The
datasheet schematic on p1 shows two diodes with anodes tied together
(pin 3 = common A; pins 1, 2 = cathodes K1, K2). Used for bias
isolation / clamping. Quote from datasheet: V_R=40V, I_F=250 mA,
V_F=320 mV typ @ 1 mA, AEC-Q101 qualified.

### Schottky alternatives we DO have ground-truth for
If the design has flexibility on which Schottky topology to use, these
are ready to build factories for:
- **MBRS340T3G** — DONE. Factory in `diodes.py`.
- **PMEG2010EJ** — Nexperia signal Schottky, 1 A, 20 V, SOD-323. Full
  SamacSys archive present, **datasheet missing from `Research/`** —
  fetch from Nexperia website.

### `TPS259621DDAR` (TI eFuse, SOIC-8 + EP)
DONE — `Research/tps2596.pdf` (SLVSET8A, May 2019 rev A) was added.
Factory in `efuses.py::add_tps259621ddar`. The family doc covers
TPS259620/621/630/631; this part is the **OVC pin-selectable +
auto-retry** variant.

### `AD8603` Research-folder filename mismatch
The PDF in `Research/AD8603ARJZ-R2.pdf` has an "R" suffix that doesn't
appear in the AD8603 family Ordering Guide — only AUJZ variants are
listed. The file IS the AD8603/8607/8609 family datasheet (Rev D).
Treat the filename as a labelling typo; the factory uses canonical
`AD8603AUJZ-R2` per SamacSys.

---

## 4. Bulk data gaps (apply to every factory)

These would be filled by a single sweep across all parts, not per-part.

### Distributor data
- **Pricing** (1 pc and 20 k pc tiers, in EUR or USD).
  Source: live quote from Mouser / Farnell / DigiKey / Arrow.
  Script idea: take every `manf_pn` from `Design.chips`, hit the
  Mouser API, populate `currency` + `price_1pc` + `price_20kpc`.

### Country-of-origin
- **`fab_country`** unknown for every part except in cases where Mouser
  surfaces the COO in the product listing.
  Source: Mouser product page → "Country of Origin" field, or a
  vendor-supplied traceability matrix.
  Validator `_v_fab_country_allowed` currently no-ops when
  `fab_country=None` — so the CN/TW exclusion can't fire on
  the current catalog.

### Material data
- **`body_material`, `lead_material`, `density_g_cm3`, `youngs_modulus_gpa`, `cte_ppm_k`**
  unknown for every chip. Needed for the structural-shock FEM
  simulation at launch (1000+ G axial).
  Source: vendor material declaration forms (FAE request) or generic
  package-material standards (epoxy mold compound + Sn-plated Cu
  leadframe for plastic SO/SOT/QFN; SAC305 solder balls for BGA/DSBGA;
  alumina substrates for ceramic packages).

### Export-control
- **`eccn`, `itar`** unknown for every part. For commercial
  semiconductors typically EAR99, but assert per-part.
  Source: vendor export-classification page (Mouser surfaces ECCN on
  the product listing).

---

## 4b. Datasheets to fetch into Research/

These factories were built from SamacSys ground-truth (pins +
geometry are exact) but their datasheets aren't in `Research/`. The
factory's `datasheet=None` (and tests skip the resolves-check):

| factory | reason | source |
|---|---|---|
| `add_as4c512m16d3lc_12bin` | DONE — `Research/ALLM-S-A0015858505-1.pdf` added. Factory updated. |  |
| `add_awr2944abgaltq1` | DONE — `Research/TXII-S-A0027608501-1.pdf` (AWR2943/2944/2944LC family, SWRS273D) added. **Also surfaced an order-code mistake**: an earlier BOM iteration referenced `AWR2944ALBGALTRQ1` (LC, 3 MB) — design needs the full 4 MB variant. Resolved by adding `add_awr2944abgaltrq1` (full AWR2944, T&R) as the production factory. |  |
| `add_awr2243abgablq1` | DONE — `Research/awr2243.pdf` (SWRS223D Feb 2024) added. Factory updated. T&R sibling `add_awr2243abgablrq1` also added for production. |  |

## 4c. Per-factory follow-ups (batch 3)

### `add_we_744043100` (Würth WE-PD inductor)
- DCR, I_sat, SRF not transcribed — fetch from Würth REDEXPERT or product page.

### `add_st25dv16kc_ie8t3` (ST NFC dual-port tag)
- I²C address strapping logic, ISO 15693 specifics, energy-harvest output current not transcribed. Datasheet present but not deep-read.

### `add_drv8833pwr` / `add_drv8711dcpr` (TI motor drivers)
- Abs max V_M for 8833, full SPI register map for 8711 not transcribed. Datasheets present.

### `add_s25hl512tfamhi010` (Infineon HyperFlash)
- The PDF filename in Research/ is `S25HL512TDPMHI010.pdf` (TDP suffix) but the SamacSys part is `S25HL512TFAMHI010` (TFA suffix). May be different variants of the same family — verify on next refresh.

### `add_mt29f4g01abafd12_aat_f` / `add_mt29f8g08abacawp_it_c`
- Both share their family datasheets with the parent variants (`MT29F4G01ABAFDWB-IT_F.pdf` and `MT29F8G08ABACAH4-IT_C.pdf` respectively). The AAT/AWP suffixes differ in package/qualification only.

### `add_stm32g0b1kct6n` / `kcu6n` / `rei6n` (STM32G0B1 LQFP/QFN/BGA)
- All three reference the same datasheet (`STM32G0B1KCT6N.pdf`). ST publishes one datasheet for the family; package differs.

### `add_stm32wle5jci6` (LoRa SoC)
- RF matching network values not transcribed — see ST AN5457.

### `add_stm32mp255fak3` (424-ball BGA application processor)
- 424 pins parsed verbatim from KiCad sym. Power-domain mapping, DDR3 ball-to-controller routing, and high-speed lane assignments not yet structured beyond raw pin names. Refer to ST AN5724 for DDR3 routing.

### `add_lbee5kl1yn_814` (Murata WiFi+BT module)
- Antenna option (internal trace vs U.FL), RF certification numbers (FCC/IC/CE) not transcribed.

### `add_stpmic25apqr` (STM32MP25 companion PMIC)
- Per-rail voltage / current ratings, I²C address map not transcribed.

### `add_iwr1843arqgalpr` / `add_awr2944abgaltq1` / `add_awr2243abgablq1` (TI radar)
- Pin lists parsed verbatim. Antenna feed pinout (TX/RX channels), boot-mode straps, JTAG pins not yet structured as named groups.

### `add_adf4351bcpz` (ADI PLL)
- SPI register map, lock-detect output, loop-filter design notes not transcribed.

## 4d. JEDEC standard package observation

When a part's SamacSys archive doesn't include a KiCad symbol (only a
STEP 3D model, common for image sensors and ONFI-standard NAND flash),
the catalog approach is:

1. **Reuse footprint from another part that uses the same JEDEC
   package class.** Example: MX60LF8G28AD-XKI (Macronix NAND, no
   SamacSys KiCad sym) reuses the Micron MT29F8G08ABACAH4's
   `BGA63C80P10X12_900X1100X100.kicad_mod` because both are the JEDEC
   ONFI VFBGA-63 standard package (9×11×1.0 mm, 0.8 mm pitch, identical
   ball pattern). Verified by coverage check at factory-build time.

2. **Transcribe pin map from the part's own datasheet** to populate
   the functional names (since pin assignment, while standardised by
   ONFI, varies by part for vendor-specific features).

3. **Add `Footprint.source` and `Footprint.note` explaining the reuse**
   so the cross-vendor inheritance is auditable.

Status: applied to MX60LF8G28AD-XKI-T (NAND). The same approach can be
applied to other ONFI parts and to JEDEC TSOP/SOIC footprints when
SamacSys lacks the specific PN.

## 4e. Datasheet-derived factories (no SamacSys KiCad symbol)

These factories hand-typed their pin lists from the datasheet because
SamacSys provided only a STEP file (no KiCad symbol):

| factory | source | footprint source |
|---|---|---|
| `add_ar0234cssm00suka0_cp` | datasheet Table 3 (83-ball CSP) | project's `ODCSP-83_AR0234CS` (built via `gen_lga_footprint.py` from datasheet Case 570CK Issue A) |
| `add_mx60lf8g28ad_xki_t` | datasheet §3 ball diagram (VFBGA-63) | reused from Micron MT29F8G08ABACAH4 (JEDEC ONFI standard) |

## 5. Process improvements (for the catalog itself)

- **Validator: surface "footprint not from SamacSys"** — currently
  `BSS138LT1G` has `Footprint.source = "onsemi-datasheet"`. A validator
  could collect every chip whose footprint source ≠ "samacsys" and flag
  them for SamacSys upgrade. Low priority — the BSS138 footprint is
  datasheet-faithful, just less mature.

- **Validator: surface chips with `note` containing "NOT STATED"** —
  could grep notes for that string to enumerate parts that need
  follow-up sourcing/material data.

- **Test helper: shared MOSFET / LDO / etc. test base class** — every
  factory currently re-implements the same `field unset` /
  `validators pass` / `artifact present` patterns. Could be factored
  out into a `_factory_test_base.py` once we have ~10 factories and
  the pattern is stable.

- **One-shot script `tools/sourcing_sweep.py`** — iterate over the
  whole catalog, hit Mouser API, write back `currency` + `price_1pc` +
  `fab_country` to a sidecar JSON that factories read on import. Keeps
  the per-part Python sources free of churning live data.
