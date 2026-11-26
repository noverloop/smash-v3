# Bring-up plan — tower on the dev panel

First power-on of a built dev panel (the flat tower on its tiles + the programmer
strip), one power state at a time. Each stage lists what to switch on, what to
measure and where, what "pass" is, and what to suspect if it fails. Do not pot
anything until the whole plan passes.

Probe points (all on the dev panel, none on the tower boards):
- `TP_DEV_DBG_<net>` on the **programmer strip** for rails and control lines that
  have a sleeve lane (reached over the channel bus), and just outside the tile for
  board-local debug nets (radar JTAG and rails, activation MAG_1V8 / TMR_VDD).
- The **rail monitor** (U_DEV_MON1-3, ADS7138) reads the rails marked MON in the
  table and logs them at every stage (FIRMWARE_RULES #25).
- **Per-tile current**: each consumer tile's BAT_PROT, 3V3, COMP_5V and COMP_3V3
  reach the bus through its own 0.1 Ω shunt R_DEV_SH_<RAIL>_<TILE> (1 mA = 0.1 mV),
  with TP_DEV_SH_…_T / _B either side where there is room. Lift a shunt to cut a tile
  off that rail.
- Rails with neither are measured on the capacitor named in the table (the tiles
  are open on the panel).

Voltages are nominal; pass = within ±5 % unless stated.

## 0. Equipment and safety

- Bench supply with current limit, set per stage (below). Scope ≥ 100 MHz, 4
  channels (power-up sequencing), DMM, µA meter (or the dev board's PAC1941 +
  INA241), frequency counter / scope for clocks.
- **ACTIVATE_HV is 33 V** and drives the parachute-cutter wires: leave the
  clamp tabs (P_ACT_WIRE_*, P_ACT_COL_*) open or on dummy loads until stage 6.
- ESD: wrist strap. The aft-crown signal lanes have ESD arrays (U_ESD_*) and
  100 Ω series resistors at the MCU pins, EXT_VIN a TVS, the cutter columns 36 V
  TVSs; the internal tile pads (test points, castellations) are unprotected.
- Bench supply for a real tower: CV mode, its own OVP at 6.0 V, current limit
  ≤ 1 A (D_EXT_IN is a 1 A diode; fixture-power tests stay ≤ 1 A of load — the
  cutter and fins need the cells). The dev board cuts both power paths above
  ≈ 5.9 V (U_DEV_OVP) and only powers a tower with all three seat teeth closed.

## Known behaviours (by design — not faults)

- **ACTIVATE_HV ≈ 4.7 V in Ready** with the cutter boost disabled: the
  non-synchronous TPS61175 passes COMP_5V_RAW through its inductor + diode.
  No wire current flows (master, row and column switches all open); the bleed +
  monitor draw ≈ 90 µA. 33 V appears only with ACTIVATE_BOOST_EN (rule #30).
- **SWD to the WBA55 and the fin MCU ≤ 2 MHz**: 1 kΩ series resistors at their
  pins (crown protection). The MP25 lines have 100 Ω and run at full speed.
- **TP_VDD on the crown is 3V3_AON through 1 kΩ**, not the MP25's I/O rail
  (COMP_3V3, off in Standby). A third-party probe that takes VTref from it
  could drive SWD into an unpowered MP25 — use the dev board, or check COMP_3V3.
- **PMIC INTn / RSTn**: the STPMIC25's internal pull-ups go to its VIO (3V3), so
  for the few ms between 3V3 and COMP_3V3 at power-up ≈ 40 µA flows into the
  unpowered MP25 PI4. Accepted.
- **BAT_SENSE** (WBA PA3) must be converted against VREFINT (rule #37): below a
  ≈ 3.35 V pack the WBA's ADC reference follows the pack.

## 1. Unpowered checks

1. Visual + X-ray of the BGAs (MP25, DDR3L, AWR1843AOP, WBA55, BMM350) and of the
   0.4 mm parts (S-1318 HSNT-4, BGS12, PE64904, TC78H653).
2. Polarity / orientation: pin-1 marks on every IC; LEDs and diodes (BAS40-02L
   cathode = marked end, RB160VAM, PNS40010AER); tantalums.
3. Resistance from each rail to GND (DMM, both polarities). Nothing below ~100 Ω;
   a short is most likely an assembly bridge or a wrong-orientation part.
   Rails and probe points:

| Rail | V | Probe (TP or cap) | MON | Board | On in state |
|---|---|---|---|---|---|
| BAT_RAW | 3.0–4.07 | R_BAT1_ISO..3 (or the PAC1941 bus voltage, flat tower) | | power | shelf |
| TMR_VDD | 3.3 | TP_DEV_DBG_TMR_VDD | 2.4 | activation | shelf |
| BAT_PROT | 3.0–4.07 | TP_BAT (wakeup) / CBAT3; per tile TP_DEV_SH_BAT_PROT_* | 3.5 | power | aon |
| 3V3_AON | 3.3 | C_WBA_BULK_1 (TP_VDD through 1 k) | 2.3 | wakeup | aon |
| WBA_VDD11 | 1.1 | C_WBA_VDD11 | | wakeup | aon |
| REG_IN_MAIN | = BAT | TP_DEV_DBG_REG_IN_MAIN | 2.1 | power | main |
| 3V3 | 3.3 | COUT1; per tile TP_DEV_SH_3V3_* | 2.2 | power | with COMP_5V_RAW |
| MAG_1V8 | 1.8 | TP_DEV_DBG_MAG_1V8 | 2.5 | activation | with 3V3 |
| LR_VBAT | 3.3 | C_LR_BULK_1 | | wakeup | with 3V3 |
| LR_VDCC | 1.55 | C_LR_VDCC1 | | wakeup | main (LR2021 on) |
| XV_LO_3V3 | 3.3 | C_XV_LO_BULK_4 | | wakeup | with 3V3 |
| COMP_5V_RAW | 5.02 | TP_DEV_DBG_COMP_5V_RAW | 2.0 | power | main |
| COMP_BST_VCC | ≈4.25 | C_BOOST_VCC_1 | | power | main |
| COMP_5V | 5.02 | TP_DEV_DBG_COMP_5V | 1.7 | power | main |
| COMP_3V3 | 3.3 | TP_DEV_DBG_COMP_3V3 | 1.0 | power | PMIC rank 1 |
| COMP_1V8_AON | 1.8 | TP_DEV_DBG_COMP_1V8_AON | 1.1 | power | PMIC rank 1 |
| COMP_0V82 | 0.82 | TP_DEV_DBG_COMP_0V82 | 1.2 | power | PMIC rank 2 |
| COMP_0V9 | 0.80 → 0.90 (firmware) | TP_DEV_DBG_COMP_0V9 | 1.3 | power | PMIC rank 3 |
| COMP_1V8 | 1.8 | TP_DEV_DBG_COMP_1V8 | 1.4 | power | PMIC rank 3 |
| COMP_1V35 | 1.35 | TP_DEV_DBG_COMP_1V35 | 1.5 | power | firmware (BUCK6) |
| COMP_2V8 | 2.8 | TP_DEV_DBG_COMP_2V8 | 1.6 | power | firmware (LDO5) |
| CAM_VAA_2V8 / CAM_VCORE_1V15 | 2.8 / 1.15 | C_CAM_VAA_BULK / C_CAM_VCORE_BULK | | camera | run |
| AWR_1V2 / AWR_1V3 / AWR_1V8 | 1.2 / 1.326 / 1.8 | TP_DEV_DBG_AWR_1V2 / _1V3 / _1V8 | 2.7 / 3.0 / 3.1 | radar | RADAR_EN |
| LR_TCXO_3V3 | 3.3 | C_LR_TCXO_MEMS2 | | wakeup | LR2021 VTCXO on |
| XV_5V | 5.0 (= COMP_5V) | C_XV_PA_BULK1 | 3.7 | wakeup | XV_PA_EN |
| ACTIVATE_HV | ≈ 4.7 (Ready) / 33.3 | TP_DEV_DBG_ACTIVATE_HV (33 V) | 2.6 | power | ≈ 4.7 V with COMP_5V_RAW; 33.3 V with ACTIVATE_BOOST_EN (#30) |
| HALL_VIN | ≈ 3.2 (150 Ω from 3V3) | crown contact HALL_VIN | | activation | with 3V3 |
| NRST (MP25 / PMIC RSTn) | 3.3 when released | R_PMIC_NRST | 3.6 | power / compute | PMIC POWER_UP done |
| DEV_VBUS / DEV_3V3 | 5.0 / 3.3 | C_DEV_LDO_IN / TP_DEV_MCU_3V3 | | dev strip | USB |

MON = rail monitor chip.channel (1.0 = U_DEV_MON1 AIN0). Control lines on the strip:
TP_DEV_DBG_COMP_OUT, _IR_WAKE, _PWR_HOLD, _PMIC_PWR_OK, _ACTIVATE_BOOST_EN,
_MAIN_SW_GATE, _RADAR_EN (PWR_HOLD, PMIC_PWR_OK and RADAR_EN also on MON 3.3 / 3.2 / 3.4).

## 2. Programmer strip alone (USB only, tower switches off)

- Current limit: USB host. Plug a USB-C to USB-C cable (CC Rd 5.1 k on the strip).
- Pass: DEV_VBUS 5.0 V, DEV_3V3 3.3 V; LED D_DEV_LED_VBUS + D_DEV_LED_3V3 on.
- Program the probe MCU (U_DEV_MCU, STM32U535) through TP_DEV_MCU_SWCLK / SWDIO /
  NRST with an external CMSIS-DAP; BOOT0 via S_DEV_MCU_BOOT if blank.
- Pass: it enumerates as CMSIS-DAP + CDC; on its I²C the PAC1941 answers at 0x10 and
  the rail monitors at 0x11 / 0x12 / 0x13 (all channels ≈ 0 V, tower off).

## 2b. Dev-board protection (before any tower is seated)

With the socket EMPTY and the flat tower switches off, current-limited bench (≤ 100 mA):
- Reverse the leads at J_DEV_BENCH: D_DEV_LED_INPROT on, DEV_BENCH ≈ 0 V, nothing
  downstream sees a negative voltage; DEV_INPROT_FAULT (PA15) low.
- Ramp the bench 3 → 7 V with the TWR path enabled into a 100 Ω dummy: the TWR
  path drops at ≈ 5.9 V (D_DEV_LED_OVP, PB10 high), the input protection at
  ≈ 6.5 V. With the FLAT path enabled: it drops at ≈ 4.37 V (D_DEV_LED_OVP_FLAT).
- Seat interlock: with a tower seated, lift each seat tooth in turn (or open its
  spring pin): tower power must drop each time; the flat path must stay off while
  any seat tooth touches.
- Soft start: scope the TWR path output into the dummy + 220 µF — ≈ 1 ms ramp, no
  overshoot; PAC1941 sense voltage within its limits.
- Probe firmware reports the three status lines (rule #40).

## 3. Shelf (battery side only)

- Bench → DEV_FEED → Q_DEV_FLAT_PWR → flat tower BAT_RAW at **3.6 V, 20 mA limit**
  (probe firmware refuses > 4.3 V for the flat tower).
- Pass: BAT_RAW 3.6 V; TMR_VDD 3.3 V; 3V3_AON **off**; supply current a few µA
  (S-1318 Iq + the RR123 shelf sensor). mA-level current = a short or a part
  backwards on BAT_RAW / TMR_VDD.
- Short or high current later on: read the per-tile shunts (mV across
  R_DEV_SH_*, 0.1 Ω) to find the tile; for µA-level excess, lift the shunts one
  tile at a time and watch the total.

## 4. Always-on (WBA)

- Hold **S_DEV_JUMP** (JUMP_WAKE): it opens Q_AON_EN → 3V3_AON. A blank WBA cannot
  hold power yet, so keep the button held while programming it.
- Pass: 3V3_AON 3.3 V, WBA_VDD11 ≈ 1.1 V, current < 10 mA.
- Program the WBA55 through the fixture (TWR_WBA_SWCLK / SWDIO / NRST, or
  TP_WBA_* on the panel); first firmware = hold WBA_AON_HOLD, blink, report.
- Release the button: 3V3_AON stays up (held by firmware).
- Standby current with the WBA in Stop mode: target ≤ 28 µA total (resistive
  share ≈ 4 µA through RAON_PU). Check the wake inputs:
  - magnet at the DRV5032 → MAG_WAKE_N low (level),
  - tap the piezo / S_DEV_LAUNCH → COMP_OUT pulse → MAG_WAKE_N pulse (Q_SHOCK_WAKE),
  - IR at a VEMD5110 → IR_WAKE (TP_DEV_DBG_IR_WAKE).
  COMP_OUT on TP_DEV_DBG_COMP_OUT. The AON hold path has 1.0 mm probe pads on the
  wakeup tile: TP_AON_EN (≥ 1.0 V = LDO on; ≈ 3.0 V when held by PB15 through
  DHOLD_AON, ≈ BAT_RAW while a wake source holds Q_AON_EN) and TP_WBA_AON_HOLD.
  If the WBA drops out on releasing S_DEV_JUMP: TP_WBA_AON_HOLD low = firmware
  not driving PB15 (rule #37b).
  FIRMWARE_RULES #10, #21, #24.

## 5. Main power and the PMIC start-up

- Current limit **300 mA**, then 1 A once the PMIC sequence is seen.
- WBA closes QMAIN (main switch on power_board, gate on TP_DEV_DBG_MAIN_SW_GATE)
  → REG_IN_MAIN; Q_ISO turns fully on with it (R_ISO_EN_PU);
  the LTC3124 starts (SD pulled up) → COMP_5V_RAW → 3V3 (U_PWR buck) → LR/XV/MAG
  rails; COMP_5V → PMIC turns on.
- **LTC3124 loop check** (compensation computed for ≈ 72 µF effective on
  COMP_5V_RAW: RC 107 k, CC 820 pF, CF 220 pF; crossover ≈ 8 kHz): bench at
  2.5 V, step the COMP_5V_RAW load 0.2 → 1.2 A (electronic load on
  TP_DEV_DBG_COMP_5V_RAW). Pass: ≤ 2 ringing cycles, overshoot ≤ 150 mV, no
  oscillation at light load. A Bode injection across R_BOOST_R1 (10 Ω insert)
  should show ≥ 45° phase margin; adjust RC / CC if not.
- **Scope the PMIC sequence** on 4 channels at the strip test points:
  TP_DEV_DBG_COMP_3V3, _COMP_1V8_AON, _COMP_0V82, _COMP_1V8 (trigger on
  TP_DEV_DBG_COMP_5V). The rail monitor logs all PMIC rails at once (≈ 1 ms
  resolution) as a cross-check; the scope capture is the pass/fail.
  - Pass: COMP_3V3 and COMP_1V8_AON rise together (rank 1, ≈ 7 ms after VIN;
    within 1 ms of each other — MP25 DS §6.3.2), COMP_0V82 ≈ 1.5 ms later,
    COMP_0V9 + COMP_1V8 at rank 3, then NRST (PMIC RSTn → MP25 NRST) releases (probe R_PMIC_NRST on
    the power tile) and PMIC_PWR_OK goes high (TP_DEV_DBG_PMIC_PWR_OK).
  - Fail on the order = stop: MP25 damage risk.
- Clocks (pass = frequency ±100 ppm, amplitude at the consumer):
  Y_MPU_HSE 40 MHz (1.8 V), Y_MPU_LSE 32.768 kHz, Y_WBA_HSE 32 MHz.
  MP25 OSC_OUT (R2) reads 0 V (R_MPU_OSC_OUT 100 Ω to GND): the boot ROM must
  select HSE **digital bypass** — confirm in the TF-A boot log / RCC (AN5489 §4.1.1).
- Monitor log: BAT_PROT (MON 3.5) within ≈ 50 mV of BAT_RAW under load (Q_ISO
  on); NRST (MON 3.6) high and steady — a dip there is a PMIC restart (rule #32).
- PWR_HOLD (TP_DEV_DBG_PWR_HOLD) high once the MP25 holds power. Q_ISO on:
  BAT_RAW − BAT_PROT < 50 mV at a few hundred mA (not a 0.6 V diode drop).
- MP25: probe drives PB13 **low** (BOOT0/BOOT2 → serial boot, FIRMWARE_RULES #6);
  console on TWR_CONS_TX/RX through the probe. Load TF-A over UART/USB.
- TF-A: provision the PMIC NVM (FIRMWARE_RULES #1), enable BUCK6 1.35 V
  (#3), raise BUCK1 to 0.9 V; check COMP_1V35 and DDR3L_VREF (0.675 V, the
  local 1k/1k divider).
- DDR training passes; write the SPI-NAND; release PB13 → BOOT high → boots from NAND.
- I²C scans (pass = exactly these addresses):
  I²C2: BMM350 0x14, ISM330 (IMU1) 0x6A, MCP9808 0x1A, STPMIC25 0x33;
  I²C3: H3LIS331 0x18, IMU2 0x6A, IMU3 0x6B; SYS_I2C: VB1943 0x10.
- WBA ↔ MP25: UART (USART2 ↔ LPUART1) and the HCI SPI3 link; WBA_RST_CMD resets it.

## 6. Subsystems (one at a time, current noted for each)

- **Fin-deploy Hall**: HALL_VIN ≈ 3.2 V at its crown contact (≈ 2.8 V with the
  DRV5023 drawing 3 mA); FIN_HALL toggles with the magnet.
- **Fin MCU** (STM32U545): SWD through TWR_FIN_* (≤ 2 MHz, 1 kΩ series); SYS_SPI to the MP25; fin
  drivers TC78H653 on COMP_5V_RAW — STBY low until firmware, check each H-bridge
  into a dummy load.
- **Radar** (AWR1843AOP): PI6 holds NRESET low, RADAR_EN high (TP_DEV_DBG_RADAR_EN)
  → AWR_1V2 / 1V3 / 1V8 (TP_DEV_DBG_AWR_*; current on R_DEV_SH_*_RADAR); release NRESET ≥ 5 ms later (#12). 40 MHz at Y_AWR_HSE (≈ 0.98 Vpp at CLKP).
  Flash the QSPI image in SOP5 (quad), then functional boot; SPI + RS232 to the MP25.
- **Camera** (VB1943): LDO5 (COMP_2V8) on, VANA ≥ 100 µs before CAM_NRST (#14);
  27 MHz at Y_CAM_EXTCLK; I²C 0x10; CSI lanes to the MP25.
- **LoRa / S1** (LR2021): VTCXO on → LR_TCXO_3V3, 32 MHz clipped sine at XTA
  (#15); SPI from the WBA; conducted test on J_DEV_HF_S1 (u.FL, reads ≈ 3.3 dB
  low at 2.44 GHz into 50 Ω).
- **Radar boot time** (rule #39): scope RADAR_EN → the first frame-done / DRDY
  interrupt, with and without restored calibration data; record it (the battery
  sim assumes 1 s; the boot-at-launch option depends on it).
- **S4 transverter**: XV_PA_EN → XV_5V ≈ 5.0 V (~1 ms ramp); ADF4351 lock (MUXOUT on WBA PB11
  and TP_XV_LO_MUX, #16); conducted test on J_DEV_HF_S4 (≈ 0.7 dB low at 4.7 GHz).
- **CAN**: TJA1462 VIO on COMP_3V3; probe ↔ tower CAN through the fixture (120 Ω
  each end).
- **Cutter (33 V)**: dummy loads on the wires first; ACTIVATE_BOOST_EN high (#30)
  → ACTIVATE_HV 33.3 V within ≈ 5 ms; master
  arm (PARACHUTE_CUTTER_SET) + one row + one column; pulse ≤ 10 ms (#18).

## 7. Exit criteria

- Every rail in the table within tolerance in its state (rail monitor log saved
  per stage); the PMIC sequence capture saved; standby current measured and ≤
  budget; per-tile currents recorded in each state.
- Every MCU programmed and talking on its links; every I²C address present.
- Both u.FL conducted measurements recorded.
- `FIRMWARE_RULES.md` rules exercised by the bring-up firmware ticked off.
