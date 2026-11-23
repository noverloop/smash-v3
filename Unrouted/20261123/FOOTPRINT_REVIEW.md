# Footprint review

Export 2026-11-23 from commit 3ac55e8 (generate_stackup.py, maximalist).


Every footprint in the maximalist tower, by provenance. **Self-drawn** lands were made from datasheet drawings (or project scripts) and have never been built — check pad sizes, pitch, pin 1 and the exposed pad against the datasheet before fab. **Modified vendor** lands are SamacSys/SnapMagic files we changed (land borrowed from a sibling part, 3D model rotated, pins listed from the datasheet). Positions/rotations are not part of this list.


## CHECK — self-drawn (13)

| Footprint | Part (MPN) | Refs | Board(s) | Source | Notes |
|---|---|---|---|---|---|
| `ABLIC_HSNT-4-1010` | S-1318D33-A4T2U4 | U_TMR_LDO, U_AON_LDO | activation_interface, wakeup_board | SELF-DRAWN (datasheet) | 3D model rotated (-90.0, 0.0, 0.0) by us — check pin 1 in the 3D viewer; ABLIC HSNT-4(1010) land PL004-A-L-SD-2.0 (S-1318 DS p.41) |
| `CellLead_PTH_Pin_D1` | CellLead_PTH_Pin_D1 | P_CELL_PIN_NEG1, P_CELL_PIN_NEG2, P_CELL_PIN_NEG3 | aft_end_board | SELF-DRAWN (project (Tadiran /P cell lead, placeholder Ø)) | no 3D model; Pin Ø0.8 is a placeholder until Tadiran confirms the /P lead. |
| `CellLead_PTH_Wire_D0.8` | CellLead_PTH_Wire_D0.8 | P_CELL_WIRE_POS1, P_CELL_WIRE_POS2, P_CELL_WIRE_POS3 | aft_end_board | SELF-DRAWN (project (Tadiran /P cell lead, placeholder Ø)) | no 3D model; Pin Ø0.8 is a placeholder until Tadiran confirms the /P lead. |
| `Clamp_Tab_D1.6mm` | Clamp_Tab_D1.6mm | P_ACT_COL_0, P_ACT_COL_1, P_ACT_COL_2, P_ACT_COL_3, P_ACT_WIRE_0, P_ACT_WIRE_1 +14 | aft_end_board | SELF-DRAWN (project (library_kicad/footprints.pretty/)) | no 3D model; Placeholder land; replace with the chosen clamp part. |
| `DFN8_2x2_GRF2073W_DS` | GRF2073W | U_XV_LNA | wakeup_board | SELF-DRAWN (custom) |  |
| `Infineon_TSLP-2-1` | BAS4002LE6327XTMA1 | D_ACT_WIRE_0, D_ACT_WIRE_1, D_ACT_WIRE_2, D_ACT_WIRE_3, D_ACT_WIRE_4, D_ACT_WIRE_5 +14 | aft_end_board, wakeup_board | SELF-DRAWN (Infineon BAS40 datasheet p.14 (TSLP-2-1 recommended footprint)) | no 3D model |
| `MCHP_MC_DFN-8_2x3` | MCP1640CT-I/MC, MCP1640D-I/MC | U_BOOST, U_XV_BOOST | power_board, wakeup_board | SELF-DRAWN (datasheet) | no 3D model |
| `MT03_092_QPD_TO8` | MT03-092 | U_QPD | qpd_module | SELF-DRAWN (project (library_kicad/footprints.pretty/)) | no 3D model; 6 through-hole pads in TO-8 outline (Ø15.4 mm), two rows of 3 at 2.54 mm pitch, rows 10.16 mm apart (DS p2). Pads 4/6/3/1 = quadrant anodes Q1/Q2/Q3/Q4, pad 2 = common cathode (backside butt weld), pad 5 = NC. Pin numbering follows datasheet. |
| `PiezoDisc_SMD10T04R111` | SMD10T04R111 | P_PIEZO | aft_end_board | SELF-DRAWN (project (library_kicad/footprints.pretty/)) | no 3D model; 2 SMD pads under the Ø10 disc: main electrode (centre-offset Ø5 round) + wrap strip (2.5×1.6 at the east rim). Electrode split per Steminc R config — verify strip position against the factory drawing before fab. |
| `Pogo_Pad_D2.0mm` |  | TP_SPI_CS_FIN, TP_SPI_MISO, TP_SPI_SCLK, TP_FIN1_A2, TP_FIN1_B1, TP_FIN1_B2 +39 | activation_interface, aft_end_board, aft_end_cap, dev_diag | SELF-DRAWN (project (library_kicad/footprints.pretty/)) | no 3D model; Single SMD circle pad, 2.0 mm Ø. |
| `Pogo_Pad_S2.0mm` |  | TP_SPI_MOSI, TP_FIN1_A1, TP_FIN2_A1, TP_FIN3_A1, TP_FIN4_A1, TP_CAN_N +10 | aft_end_board, aft_end_cap | SELF-DRAWN (project (library_kicad/footprints.pretty/)) | no 3D model; Single SMD square pad, 2.0 mm — group-start marker. |
| `QFN16_3x3_GRF5126_DS` | GRF5126 | U_XV_PA | wakeup_board | SELF-DRAWN (custom) | 3D model rotated (-90.0, 0.0, 0.0) by us — check pin 1 in the 3D viewer |
| `VSMB1940X01` | VSMB1940X01 | D_IR_TX_Q, D_IR_TX, D_IR_TX_U, D_IR_TX_C | camera_module, qpd_module, radar_module, usb_nose | SELF-DRAWN (authored) | no 3D model; Hand-authored from DS 81933 Rev 1.6 package drawing 6.541-5064.01-4 + recommended solder pad (2× 1.0 × 1.45 mm, 0.6 mm gap). No STEP model. |

## CHECK — vendor land modified by us (18)

| Footprint | Part (MPN) | Refs | Board(s) | Source | Notes |
|---|---|---|---|---|---|
| `1SS294LFT` | SSM3K7002KFU,LF | Q_HEALTH_COIL, Q_PARACHUTE_CUTTER_ACTIVATE_LS, Q_ACT_ROW0_LS, Q_ACT_ROW1_LS, Q_ACT_ROW2_LS, Q_ACT_ROW3_LS +4 | activation_interface, aft_end_board | vendor (samacsys) | land named after another part (1SS294LFT) — confirm it is the same package |
| `BGA74C80P9X10_890X1030X220` | VB1943CAJX/1 | U_CAM | camera_module | vendor (samacsys) | 3D model rotated (-90.0, 0.0, 0.0) by us — check pin 1 in the 3D viewer |
| `BGA96C80P9X16_800X1400X120` | MT41K256M16TW-107 IT:P | U_DDR | companion_compute | vendor (samacsys) | vendor land/model taken from a sibling part (MT41K256M16TW-107_PTR) — confirm the package is identical |
| `BLM18SP221SN1B` | BLM18PG221SN1D | FB_LR_VBAT, FB_XV_LO | wakeup_board | vendor (samacsys) | land named after another part (BLM18SP221SN1B) — confirm it is the same package |
| `BUK6D12060PX` | BUK6D120-60PX | Q_PARACHUTE_CUTTER_ACTIVATE, Q_ACT_ROW0, Q_ACT_ROW1, Q_ACT_ROW2, Q_ACT_ROW3, Q_ISO +3 | aft_end_board, dev_diag, power_board, usb_nose | vendor (samacsys) | 3D model rotated (90.0, 0.0, 90.0) by us — check pin 1 in the 3D viewer |
| `Ceramic_QFN_5032_10pins` | SiT5356AECFQ-33N0-32.000000T | Y_LR_TCXO_MEMS | wakeup_board | vendor (samacsys) | vendor land/model taken from a sibling part (SiT5356AECFQ-33N0-20.000000) — confirm the package is identical |
| `DSC1001CI50080000` | DSC1001CI1-027.0000, DSC1001CI5-024.0000, DSC1001CI5-032.000 | Y_CAM_EXTCLK, Y_AWR_HSE, Y_MPU_HSE, Y_WBA_HSE, Y_DEV_HUB | camera_module, companion_compute, dev_diag, radar_module, wakeup_board | vendor (samacsys) | vendor land/model taken from a sibling part (DSC1001CI5-008.0000) — confirm the package is identical; CDFN/DFN 2.5×2.0×0.85 mm 4-pad MEMS oscillator footprint. Pin 1 (STANDBY#) at bottom-left, going counter-clockwise. |
| `HDRV40W64P254X254_2X20_5080X508X869P` | 61304021121 | J_DEV_TWR_IO, J_DEV_FLAT_IO | dev_diag | vendor (samacsys) | land named after another part (HDRV40W64P254X254_2X20_5080X508X869P) — confirm it is the same package |
| `LEDC1608X90N` | LTST-C190GKT, LTST-C190KRKT | D_DEV_SEAT1, D_DEV_SEAT2, D_DEV_SEAT3, D_DEV_LED_VBUS, D_DEV_LED_3V3, D_DEV_LED_TWR +3 | dev_diag | vendor (samacsys) | land named after another part (LEDC1608X90N) — confirm it is the same package; SamacSys 0603 chip-LED footprint. Pin 1 = cathode (silkscreen chamfer at -X,-Y corner of F.Fab marks it). Chip-LED naming: LEDC1608X90N = LED-Chip, 1608 metric size, 0.90 mm height. |
| `LIS3DHTR (LGA-16)` | H3LIS331DLTR | U_HACC | activation_interface | vendor (samacsys) | land named after another part (LIS3DHTR (LGA-16)) — confirm it is the same package; TFLGA-16L footprint shared with the LIS3DH family — SamacSys supplied as `LIS3DHTR.kicad_mod`. |
| `LQG15WH0N7B02D` | LQG15HS1N3S02D | L_XV_PA_IN | wakeup_board | vendor (samacsys) | land named after another part (LQG15WH0N7B02D) — confirm it is the same package |
| `QFN50P200X200X50-10N-D` | PE64904D-Z | U_LR_DTC1, U_LR_DTC2 | wakeup_board | vendor (samacsys) | vendor land/model taken from a sibling part (PE64904C-Z) — confirm the package is identical |
| `SHDR2W70P0X500_1X2_1000X750X1150P` | 691137710002 | J_DEV_BENCH | dev_diag | vendor (samacsys) | land named after another part (SHDR2W70P0X500_1X2_1000X750X1150P) — confirm it is the same package |
| `SON127P600X500X80-9N-D` | MX25V8035FZNI | U_AWR_FLASH | radar_module | vendor (samacsys) | vendor land/model taken from a sibling part (SST26VF080A-104I_MF) — confirm the package is identical |
| `SON50P300X500X80-17N` | LTC3124EDHC#TRPBF | U_COMP_BOOST | power_board | vendor (snapmagic) | 3D model rotated (-90.0, 0.0, 90.0) by us — check pin 1 in the 3D viewer |
| `SSM3J64CTCL3F` | SSM3K35CTC,L3F | Q_IR_TX_Q, Q_IR_TX, Q_IR_TX_U, Q_IR_TX_C, Q_CAM_SCL, Q_CAM_SDA +9 | camera_module, power_board, qpd_module, radar_module, usb_nose, wakeup_board | vendor (samacsys) | land named after another part (SSM3J64CTCL3F) — confirm it is the same package |
| `STM32MP255FAL3` | STM32MP257FAL3 | U_MPU | companion_compute | vendor (samacsys) | vendor land/model taken from a sibling part (STM32MP255FAL3) — confirm the package is identical |
| `UDB_VARIATIONA` | LTC5552IUDB#TRMPBF | U_XV_MIX | wakeup_board | vendor (samacsys) | vendor land/model taken from a sibling part (LTC5549IUDB) — confirm the package is identical; land named after another part (UDB_VARIATIONA) — confirm it is the same package |

## vendor, unchanged (44)

| Footprint | Part (MPN) | Refs | Board(s) | Source | Notes |
|---|---|---|---|---|---|
| `0906015207614110` | 0906-0-15-20-76-14-11-0 | P_DEV_FIX_00, P_DEV_FIX_01, P_DEV_FIX_02, P_DEV_FIX_03, P_DEV_FIX_05, P_DEV_FIX_06 +51 | dev_diag | vendor (samacsys) |  |
| `5849000150000030` | 5849-0-00-15-00-00-03-0 | P_DEV_DOWEL1, P_DEV_DOWEL2, P_DEV_DOWEL3 | dev_diag | vendor (samacsys) |  |
| `B3U-1000P` | B3U-1000P | S_DEV_MP25_RST, S_DEV_WBA_RST, S_DEV_WAKE, S_DEV_JUMP, S_DEV_LAUNCH, S_DEV_METER +1 | dev_diag | vendor (samacsys) |  |
| `BGA180C80P18X18_1500X1500X96` | AWR1843ARBGALPQ1 | U_AWR | radar_module | vendor (samacsys) |  |
| `BGA4C50P2X2_100X100X69` | MAX9064EBS+TG45 | U_COMP_PZ | aft_end_board | vendor (samacsys) |  |
| `BGA59C50P8X8_500X500X60` | STM32WBA55UGI7 | U_WBA | wakeup_board | vendor (samacsys) |  |
| `BGA64C50P8X8_500X500X60` | STM32U545REI6Q | U_FIN_MCU | activation_interface | vendor (samacsys) |  |
| `BGA6C40P2X3_80X120X50` | TPS62088YFPR | U_AWR_BUCK13 | radar_module | vendor (samacsys) |  |
| `BGA9C40P3X3_128X128X54` | BMM350 | U_MAG | activation_interface | vendor (samacsys) |  |
| `DRV5032AJDMRR` | DRV5032AJDMRR | U_MAG_WAKE | activation_interface | vendor (samacsys) |  |
| `INDPM5552X200N` | IHLP2020BZER100M01 | L_ACTIVATE | power_board | vendor (samacsys) |  |
| `LGA-14_1` | ISM330DLCTR | U_IMU1, U_IMU2, U_IMU3 | activation_interface | vendor (samacsys) |  |
| `LQG15HS1N8S02D` | LQG15HS1N8S02D | L_XV_LNA_BIAS | wakeup_board | vendor (samacsys) |  |
| `NCS1292` | NCS1-292+ | T_XV_IF | wakeup_board | vendor (samacsys) |  |
| `OSC_TG2016SMN_32.0000M-MCGNNM0` | TG2016SMN 32.0000M-MCGNNM0 | Y_LR_TCXO | wakeup_board | vendor (snapmagic) | no 3D model |
| `PG-TSLP-6-4` | BGS12P2L6E6327XTSA1 | U_LR_SW_HF, U_LR_IFSW, U_ANTSW_S1, U_XV_TR1, U_XV_TR2 | wakeup_board | vendor (samacsys) |  |
| `QFN40P650X650X90-57N-D` | STPMIC25APQR | U_PMIC | power_board | vendor (samacsys) |  |
| `QFN50P300X300X90-17N` | TC78H653FTG,EL | U_FIN1, U_FIN2, U_FIN3, U_FIN4 | activation_interface | vendor (samacsys) |  |
| `QFN50P300X300X90-17N-D` | PAC1941T-1E/4MX | U_DEV_INA | dev_diag | vendor (samacsys) |  |
| `QFN50P500X500X100-33N` | ADF4351BCPZ-RL7 | U_XV_LO | wakeup_board | vendor (samacsys) |  |
| `QFN50P500X500X100-33N-D` | LR2021IMLTRT | U_LR | wakeup_board | vendor (samacsys) |  |
| `QFN50P600X600X100-37N-D` | USB2514B-I/M2 | U_DEV_HUB | dev_diag | vendor (samacsys) |  |
| `QFN50P700X700X60-49N` | STM32U535CBU6 | U_DEV_MCU | dev_diag | vendor (samacsys) |  |
| `RB160VAM60` | RB160VAM-60TR | D_ACTIVATE | power_board | vendor (samacsys) |  |
| `RR123-1H02-612` | RR123-1H02-612 | U_MAG_SHELF | activation_interface | vendor (samacsys) |  |
| `SAMESKY_UJ20-C-H-G-MSMT-1A-P16-TR-67` | UJ20-C-H-G-MSMT-1A-P16-TR-67 | J_DEV_USB | dev_diag | vendor (samesky) |  |
| `SAMESKY_UJ20-C-V-G-SMT-23B-P16-TR-X5` | UJ20-C-V-G-SMT-23B-P16-TR-X5 | J_USB_C | usb_nose | vendor (samesky) |  |
| `SIT1533AIH4DCC32768E` | SIT1533AI-H4-DCC-32.768E | Y_MPU_LSE | companion_compute | vendor (samacsys) |  |
| `SON127P800X600X65-8N` | MT29F4G01ABAFDWB-IT_F | U_NAND_A, U_NAND_B | companion_compute | vendor (samacsys) |  |
| `SON50P150X200X100-8N` | TPS62822DLCR | U_CAM_BUCK_VCORE, U_AWR_BUCK12, U_AWR_LDO18 | camera_module, radar_module | vendor (samacsys) |  |
| `SON50P200X300X100-9N` | MCP9808T-E/MC | U_TMP1 | power_board | vendor (samacsys) |  |
| `SON65P300X300X100-9N-D` | TJA1462BTK/0Z | U_CAN_GW, U_DEV_CAN | dev_diag, power_board | vendor (samacsys) |  |
| `SON95P300X300X100-7N-D` | LDL112PV33R | U_PWR, U_DEV_LDO | dev_diag, power_board | vendor (samacsys) | SamacSys DFN6 (3x3) footprint. Exposed pad (pin 7) MUST be soldered to GND for thermal spec (datasheet p3 Table 1). |
| `SOP65P490X110-8N` | INA241A2IDGKR | U_DEV_ISENSE | dev_diag | vendor (samacsys) |  |
| `SOP65P640X120-14N` | SN74CB3T3125PWR | U_DEV_BUSSW0, U_DEV_BUSSW1, U_DEV_BUSSW2, U_DEV_FLATSW0, U_DEV_FLATSW1, U_DEV_FLATSW2 | dev_diag | vendor (samacsys) |  |
| `SOP65P640X120-15N` | TPS61175PWPR | U_ACTIVATE_BOOST | power_board | vendor (samacsys) | Exposed pad (pin 15) MUST be soldered to AGND for thermal. |
| `SOT95P280X100-5N` | AD8603AUJZ-R2 | U_TIA_A, U_TIA_B, U_TIA_C, U_TIA_D | qpd_module | vendor (samacsys) |  |
| `SOT95P280X145-5N` | LP5907MFX-2.8/NOPB | U_CAM_LDO_VAA | camera_module | vendor (samacsys) |  |
| `SOT95P280X145-6N` | USBLC6-4SC6 | U_DEV_ESD | dev_diag | vendor (samacsys) |  |
| `SOTFL65P210X105-3N` | RU1J002YNTCL | Q_DEV_FLAT_OE, Q_DEV_ILK_OE1, Q_DEV_ILK_OE2, Q_DEV_ILK_OE3, Q_DEV_TWR_PWR_LS, Q_DEV_FLAT_PWR_LS +3 | dev_diag | vendor (samacsys) |  |
| `SSM3J372RLF` | SSM3J372R,LF | QMAIN, Q_AON_EN, Q_LR_TCXO_SW | wakeup_board | vendor (samacsys) |  |
| `U.FL-R-SMT-1_10_` | U.FL-R-SMT-1(10) | J_DEV_HF_S1, J_DEV_HF_S4 | dev_diag | vendor (samacsys) |  |
| `VEMD5110X01` | VEMD5110X01 | D_IR_WAKE_Q, D_IR_WAKE, D_IR_WAKE_U, D_IR_WAKE_C | camera_module, qpd_module, radar_module, usb_nose | vendor (samacsys) |  |
| `WE-MAPI_4020` | 74438356047 | L_BOOST_COMP, L_BOOST_COMP_B | power_board | vendor (samacsys) |  |

## KiCad stock (standard chip passives) (8)

| Footprint | Part (MPN) | Refs | Board(s) | Source | Notes |
|---|---|---|---|---|---|
| `Capacitor_SMD:C_0402_1005Metric` | 04025A100JAT2A, 04025A101JAT2A, 04025A121JAT2A, 04025A180JAT | C_CAN_GW, C_MAG1, C_IMU1_1, C_IMU1_3, C_IMU2_1, C_IMU2_3 +180 | activation_interface, aft_end_board, camera_module, companion_compute, dev_diag, power_board, qpd_module, radar_module, wakeup_board | KiCad stock | no 3D model |
| `Capacitor_SMD:C_0603_1608Metric` | C0603C100J5GACTU, C0603C101J5GACTU, C0603C105K3RACTU, C0603C | C_MAG_C1, C_MAG2, C_IMU1_2, C_IMU2_2, C_IMU3_2, C_QPD_VREF1 +183 | activation_interface, camera_module, companion_compute, dev_diag, power_board, qpd_module, radar_module, usb_nose, wakeup_board | KiCad stock | no 3D model |
| `Capacitor_SMD:C_0805_2012Metric` | C2012X7R1H225K125AC, GRM21BR61A226ME44L, GRM21BR61E226ME44L | C_ACTIVATE_OUT_1, C_ACTIVATE_OUT_2, C_BAT_BULK1, C_BAT_BULK2, C_BAT_BULK3, C_BAT_BULK4 +12 | power_board | KiCad stock | no 3D model |
| `Capacitor_Tantalum_SMD:CP_EIA-3528-12_Kemet-T` | T491T226K010AT | C_PMIC_VIN1, CBOOST_OUT1, COUT1, COUT2, C_XV_BST_OUT | power_board, wakeup_board | KiCad stock | no 3D model |
| `Inductor_SMD:L_0402_1005Metric` | 744765010A, 744765022A, 744765027A, 744765033A, 744765039A,  | L_WBA_PI, L_LR_HF_CHOKE, L_LR_HF_TX1, L_LR_HF_TX2, L_LR_HF_RX, L_LR_HF_ANT_LPF +4 | wakeup_board | KiCad stock | no 3D model |
| `Inductor_SMD:L_2012_2.0x1.25mm` | TMS201210ALM-1R0MTAA, TMS201210ALM-2R2MTAA, TMS201210ALM-R24 | L_CAM_BUCK_VCORE, L_AWR_BUCK12, L_AWR_BUCK13, L_AWR_BUCK18, L_PMIC_FILT, L_PMIC_BUCK2 +8 | activation_interface, camera_module, power_board, radar_module, wakeup_board | KiCad stock | no 3D model |
| `Resistor_SMD:R_0402_1005Metric` | CRCW04020000Z0ED, CRCW0402100KFKED, CRCW0402100RFKED, CRCW04 | RPU_SCL_EXT, RPU_SDA_EXT, R_EXT_CAN_TERM, RPU_I2C2_SCL, RPU_I2C2_SDA, RPU_I2C3_SCL +239 | activation_interface, aft_end_board, camera_module, companion_compute, dev_diag, power_board, qpd_module, radar_module, usb_nose, wakeup_board | KiCad stock | no 3D model |
| `TestPoint:TestPoint_Pad_D1.5mm` |  | TP_MAG_DRDY, TP_IMU1_INT, TP_IMU2_INT, TP_IMU3_INT, TP_BAT, TP_3V3 +1 | activation_interface, wakeup_board | KiCad stock | no 3D model |
