# wakeup_board - collegamenti da completare a mano

Aggiornato il 12-09-2026. Totale: **80**.

Chiusi via script: 42 con via diretti, 13 con router a griglia a 6 mm, 30 dopo la riduzione
di taglia di alcuni passivi. Restano i pad dentro i gruppi piu fitti.

Da fare a mano anche i collegamenti locali dei componenti rimpiccioliti:
TMR_VDD (C_TMR_LDO), MAG_C1_TERM (C_MAG_C1), WBA_RF e WBA_RF_M (rete pi RF, da sbrogliare a mano comunque).

| Net | Aperti |
|---|---|
| 3V3 | 12 |
| 3V3_AON | 8 |
| FLEX_GND | 6 |
| BAT_RAW | 5 |
| MAIN_SW_GATE | 3 |
| AON_EN | 2 |
| AON_EN_GATE | 2 |
| REG_IN_MAIN | 2 |
| JUMP_WAKE_K | 2 |
| I2C3_SDA | 2 |
| QHOLD_GATE | 2 |
| WBA_RF | 2 |
| MAG_C1_TERM | 2 |
| WBA_NRST | 2 |
| MAG_WAKE_N | 2 |
| IMU1_SDX | 1 |
| IMU1_SCX | 1 |
| IMU1_INT | 1 |
| I2C2_SCL | 1 |
| WBA_HSE_IN | 1 |
| BOOST_OUT | 1 |
| BAT_PROT | 1 |
| MAG_SHELF_K | 1 |
| IMU3_SDX | 1 |
| IMU3_INT | 1 |
| WBA_RF_M | 1 |
| IMU2_SDX | 1 |
| WBA_VLX | 1 |
| WBA_VDD11 | 1 |
| QHOLD2_GATE | 1 |
| WBA_HCI_IRQ | 1 |
| WBA_AON_HOLD | 1 |
| IR_WAKE | 1 |
| WBA_HCI_NSS | 1 |
| WBA_HCI_SCK | 1 |
| COMP_1V8 | 1 |
| GPIO_EXT_3 | 1 |
| WBA_RST_CMD | 1 |
| TMR_VDD | 1 |
| MAG_SHELF_N | 1 |
| YAGI_WILK_B | 1 |

## 3V3 (12)
- Pista su B.Cu, lung. 0.5657 mm (-10.46,0.03) <-> Pista su F.Cu, lung. 1.1855 mm (-10.24,0.41)
- Piazzola 1 di C_IMU2_1 su B.Cu (-4.80,0.03) <-> Piazzola 1 di C_MAG2 su B.Cu (-3.68,-1.25)
- Piazzola 1 di R_IMU2_SDX_PU su B.Cu (-4.80,1.63) <-> Piazzola 1 di C_IMU2_1 su B.Cu (-4.80,0.03)
- Pista su F.Cu, lung. 1.4348 mm (-4.71,7.25) <-> Pista su B.Cu, lung. 2.0823 mm (-6.72,11.21)
- Piazzola 1 di C_IMU1_1 su B.Cu (-4.63,4.91) <-> Pista su F.Cu, lung. 2.2627 mm (-4.10,5.28)
- Piazzola 1 di RPU_I2C2_SDA su B.Cu (-3.96,-2.53) <-> Pista su B.Cu, lung. 0.7500 mm (-4.45,-4.28)
- Piazzola 1 di C_MAG2 su B.Cu (-3.68,-1.25) <-> Piazzola 1 di RPU_I2C2_SDA su B.Cu (-3.96,-2.53)
- Pista su B.Cu, lung. 0.7010 mm (-2.55,-1.58) <-> Piazzola 1 di C_MAG2 su B.Cu (-3.68,-1.25)
- Pista su B.Cu, lung. 0.7010 mm (-2.55,-1.58) <-> Pista su B.Cu, lung. 1.0850 mm (-2.24,-0.40)
- Pista su F.Cu, lung. 0.4500 mm (-1.20,3.23) <-> Pista su B.Cu, lung. 0.9560 mm (1.15,1.08)
- Piazzola 1 di RPU_I2C3_SCL su B.Cu (0.40,-6.55) <-> Pista su F.Cu, lung. 3.3713 mm (-1.20,-6.78)
- Pista su F.Cu, lung. 0.0500 mm (1.45,4.98) <-> Piazzola 1 di C_IMU1_2 su B.Cu (0.80,4.73)

## 3V3_AON (8)
- Pista su B.Cu, lung. 0.6000 mm (-3.35,4.05) <-> Piazzola 1 di C_MAG_WAKE su B.Cu (-5.96,3.53)
- Pista su B.Cu, lung. 0.2243 mm (-1.75,4.98) <-> Via su F.Cu - B.Cu (-3.25,5.50)
- Piazzola 1 di C_WBA_VDDRFPA su B.Cu (0.40,-4.25) <-> Piazzola 1 di RPU_IR_WAKE su B.Cu (-1.38,-4.60)
- Piazzola 1 di C_WBA_VDDRFPA su B.Cu (0.40,-4.25) <-> Pista su B.Cu, lung. 0.2121 mm (1.60,-2.73)
- Piazzola 1 di C_WBA_BULK_2 su B.Cu (0.80,2.63) <-> Pista su B.Cu, lung. 0.5351 mm (0.05,0.28)
- Pista su In1.Cu, lung. 1.2000 mm (4.02,1.26) <-> Piazzola 1 di C_WBA_VDDSMPS su B.Cu (3.38,2.93)
- Pista su F.Cu, lung. 0.7000 mm (7.17,0.67) <-> Piazzola G4 di U_WBA su F.Cu (8.57,0.67)
- Piazzola E12 di U_WBA su F.Cu (7.87,-0.94) <-> Pista su F.Cu, lung. 0.1618 mm (6.71,-1.25)

## FLEX_GND (6)
- Pista su B.Cu, lung. 0.0010 mm (-3.53,5.15) <-> Pista su B.Cu, lung. 0.4267 mm (-2.70,4.75)
- Pista su B.Cu, lung. 0.0010 mm (-3.53,5.15) <-> Pista su B.Cu, lung. 0.0500 mm (-4.10,5.55)
- Pista su B.Cu, lung. 0.6000 mm (4.23,-2.05) <-> Piazzola 2 di C_WBA_BULK_1 su B.Cu (3.63,-0.62)
- Pista su In1.Cu, lung. 0.4031 mm (6.47,-0.54) <-> Piazzola A12 di U_WBA su F.Cu (6.47,-0.94)
- Pista su In1.Cu, lung. 0.4031 mm (6.82,-0.34) <-> Pista su B.Cu, lung. 0.4500 mm (6.43,0.00)
- Piazzola G6 di U_WBA su F.Cu (8.57,0.27) <-> Pista su In1.Cu, lung. 0.4031 mm (7.52,0.47)

## BAT_RAW (5)
- Piazzola 38 di P_wakeup_board_spacer_fin_ble_board_wakeup_board su B.Cu (-6.85,13.44) <-> Piazzola 1 di RAON_PU su B.Cu (-1.75,2.45)
- Piazzola 1 di RMAIN_PU su B.Cu (-3.18,1.65) <-> Piazzola 1 di RAON_PU su B.Cu (-1.75,2.45)
- Pista su F.Cu, lung. 0.8267 mm (-1.25,-0.95) <-> Piazzola 1 di RMAIN_PU su B.Cu (-3.18,1.65)
- Pista su In3.Cu, lung. 1.1175 mm (5.40,5.29) <-> Piazzola 1 di C_AON_IN su B.Cu (4.50,2.60)
- Via su F.Cu - B.Cu (12.47,3.04) <-> Pista su B.Cu, lung. 0.6767 mm (12.35,5.44)

## MAIN_SW_GATE (3)
- Piazzola 2 di RMAIN_PU su B.Cu (-4.13,1.65) <-> Pista su In5.Cu, lung. 3.9589 mm (1.21,1.58)
- Piazzola 3 di QHOLD su F.Cu (5.00,-4.55) <-> Pista su F.Cu, lung. 0.7615 mm (4.79,-1.56)
- Piazzola 3 di QHOLD2 su F.Cu (9.13,-3.43) <-> Piazzola 3 di QHOLD su F.Cu (5.00,-4.55)

## AON_EN (2)
- Piazzola 2 di RHOLD_AON su B.Cu (-4.80,-5.68) <-> Piazzola 3 di U_AON_LDO su F.Cu (-1.25,0.95)
- Piazzola 3 di U_AON_LDO su F.Cu (-1.25,0.95) <-> Piazzola 3 di Q_AON_EN su F.Cu (11.17,-1.02)

## AON_EN_GATE (2)
- Piazzola 3 di D_AON_WAKE su F.Cu (-4.92,-1.10) <-> Piazzola 2 di RAON_PU su B.Cu (-2.70,2.45)
- Piazzola 3 di D_AON_WAKE su F.Cu (-4.92,-1.10) <-> Pista su F.Cu, lung. 0.4317 mm (-2.63,-6.50)

## REG_IN_MAIN (2)
- Pista su F.Cu, lung. 2.2409 mm (-8.94,3.73) <-> Pista su B.Cu, lung. 0.3889 mm (-8.14,2.15)
- Piazzola 3 di U_BOOST su F.Cu (-5.74,4.68) <-> Piazzola 6 di U_BOOST su F.Cu (-3.24,2.78)

## JUMP_WAKE_K (2)
- Piazzola 1 di D_AON_WAKE su F.Cu (-5.87,1.10) <-> Pista su B.Cu, lung. 0.4267 mm (-1.20,-5.40)
- Pista su B.Cu, lung. 1.3127 mm (-1.63,-5.72) <-> Pista su In3.Cu, lung. 7.5748 mm (-3.07,-6.65)

## I2C3_SDA (2)
- Pista su B.Cu, lung. 0.4517 mm (6.23,-2.58) <-> Piazzola 14 di U_IMU2 su F.Cu (-5.71,8.69)
- Pista su B.Cu, lung. 1.8472 mm (9.68,-4.63) <-> Pista su F.Cu, lung. 1.1950 mm (5.92,-6.42)

## QHOLD_GATE (2)
- Piazzola 1 di RHOLD_PD su B.Cu (-3.25,-2.53) <-> Piazzola 2 di RHOLD_G su B.Cu (-0.47,6.46)
- Piazzola 1 di QHOLD su F.Cu (4.05,-2.45) <-> Piazzola 1 di RHOLD_PD su B.Cu (-3.25,-2.53)

## WBA_RF (2)
- Piazzola 1 di C_WBA_PI1 su F.Cu (-2.63,0.47) <-> Piazzola 1 di L_WBA_PI su F.Cu (-1.78,5.95)
- Piazzola C2 di U_WBA su F.Cu (7.17,1.06) <-> Piazzola 1 di C_WBA_PI1 su F.Cu (-2.63,0.47)

## MAG_C1_TERM (2)
- Piazzola 5 di U_MAG su F.Cu (-8.54,-3.77) <-> Pista su F.Cu, lung. 0.0409 mm (-8.54,-2.95)
- Pista su F.Cu, lung. 0.0409 mm (-8.54,-2.95) <-> Piazzola 1 di C_MAG_C1 su B.Cu (3.48,-3.15)

## WBA_NRST (2)
- Piazzola 1 di C_WBA_NRST su B.Cu (-1.38,-3.90) <-> Piazzola 3 di Q_WBA_RST su B.Cu (-5.96,-3.88)
- Pista su B.Cu, lung. 0.4267 mm (1.05,-6.55) <-> Piazzola 1 di C_WBA_NRST su B.Cu (-1.38,-3.90)

## MAG_WAKE_N (2)
- Piazzola 2 di U_MAG_WAKE su F.Cu (2.58,9.91) <-> Pista su F.Cu, lung. 0.4572 mm (8.90,0.19)
- Piazzola G8 di U_WBA su F.Cu (8.57,-0.14) <-> Piazzola 2 di RPU_MAG_WAKE su B.Cu (4.50,-4.13)

## IMU1_SDX (1)
- Piazzola 2 di U_IMU1 su F.Cu (-8.69,1.16) <-> Piazzola 2 di R_IMU1_SDX_PU su B.Cu (1.15,-0.93)

## IMU1_SCX (1)
- Piazzola 3 di U_IMU1 su F.Cu (-9.19,1.16) <-> Piazzola 2 di R_IMU1_SCX_PU su B.Cu (3.28,-4.80)

## IMU1_INT (1)
- Piazzola 1 di TP_IMU1_INT su B.Cu (2.30,-0.45) <-> Pista su F.Cu, lung. 0.1702 mm (5.35,-12.16)

## I2C2_SCL (1)
- Microvia su F.Cu - In1.Cu (8.22,0.86) <-> Piazzola 24 di J_wakeup_board_spacer_wakeup_board_power_board su F.Cu (7.55,-10.56)

## WBA_HSE_IN (1)
- Piazzola 3 di Y_WBA_HSE su F.Cu (-3.85,-9.78) <-> Piazzola A8 di U_WBA su F.Cu (6.47,-0.14)

## BOOST_OUT (1)
- Pista su F.Cu, lung. 0.8954 mm (-3.24,3.73) <-> Piazzola 1 di CBOOST_OUT2 su B.Cu (-0.97,3.73)

## BAT_PROT (1)
- Pista su F.Cu, lung. 0.6767 mm (13.95,-4.16) <-> Pista su F.Cu, lung. 1.0409 mm (8.36,5.06)

## MAG_SHELF_K (1)
- Pista su B.Cu, lung. 0.4267 mm (2.70,3.85) <-> Piazzola 2 di D_AON_WAKE su F.Cu (-3.97,1.10)

## IMU3_SDX (1)
- Piazzola 2 di R_IMU3_SDX_PU su B.Cu (-2.55,-2.53) <-> Piazzola 2 di U_IMU3 su F.Cu (5.26,-7.08)

## IMU3_INT (1)
- Pista su F.Cu, lung. 0.3892 mm (5.26,-8.08) <-> Pista su F.Cu, lung. 0.3344 mm (7.93,-6.16)

## WBA_RF_M (1)
- Piazzola 2 di L_WBA_PI su F.Cu (-1.78,5.00) <-> Piazzola 1 di C_WBA_PI2 su F.Cu (-0.47,5.20)

## IMU2_SDX (1)
- Piazzola 2 di U_IMU2 su F.Cu (-6.37,8.03) <-> Piazzola 2 di R_IMU2_SDX_PU su B.Cu (-4.80,0.68)

## WBA_VLX (1)
- Piazzola 1 di L_WBA_SMPS su F.Cu (2.80,-2.43) <-> Piazzola C12 di U_WBA su F.Cu (7.17,-0.94)

## WBA_VDD11 (1)
- Piazzola B11 di U_WBA su F.Cu (6.82,-0.73) <-> Piazzola 1 di C_WBA_VDD11 su B.Cu (6.43,1.60)

## QHOLD2_GATE (1)
- Pista su B.Cu, lung. 0.4517 mm (3.90,-5.50) <-> Piazzola 1 di RHOLD2_PD su B.Cu (-1.85,0.03)

## WBA_HCI_IRQ (1)
- Piazzola 47 di J_wakeup_board_spacer_wakeup_board_power_board su F.Cu (-11.65,3.84) <-> Piazzola C10 di U_WBA su F.Cu (7.17,-0.54)

## WBA_AON_HOLD (1)
- Piazzola E4 di U_WBA su F.Cu (7.87,0.67) <-> Piazzola 1 di RHOLD_AON su B.Cu (-4.80,-4.73)

## IR_WAKE (1)
- Pista su In5.Cu, lung. 5.9251 mm (7.95,1.74) <-> Piazzola 2 di RPU_IR_WAKE su B.Cu (-2.33,-4.60)

## WBA_HCI_NSS (1)
- Piazzola 50 di J_wakeup_board_spacer_wakeup_board_power_board su F.Cu (-13.25,7.04) <-> Piazzola F13 di U_WBA su F.Cu (8.22,-1.14)

## WBA_HCI_SCK (1)
- Piazzola 51 di J_wakeup_board_spacer_wakeup_board_power_board su F.Cu (-13.25,5.44) <-> Piazzola G12 di U_WBA su F.Cu (8.57,-0.94)

## COMP_1V8 (1)
- Pista su F.Cu, lung. 1.1046 mm (-11.03,-5.16) <-> Piazzola 1 di C_CAM_VDD su B.Cu (-3.70,-4.13)

## GPIO_EXT_3 (1)
- Piazzola 22 di J_wakeup_board_spacer_wakeup_board_power_board su F.Cu (9.15,-10.56) <-> Piazzola 22 di P_wakeup_board_spacer_fin_ble_board_wakeup_board su B.Cu (10.75,0.64)

## WBA_RST_CMD (1)
- Piazzola 1 di Q_WBA_RST su B.Cu (-5.00,-1.78) <-> Pista su In3.Cu, lung. 2.3668 mm (-7.95,-3.24)

## TMR_VDD (1)
- Piazzola 1 di C_TMR_LDO su B.Cu (-5.96,-0.30) <-> Pista su B.Cu, lung. 0.0754 mm (-6.80,2.32)

## MAG_SHELF_N (1)
- Piazzola 2 di R_MAG_SHELF su B.Cu (1.75,3.85) <-> Piazzola 3 di U_MAG_SHELF su F.Cu (4.15,3.33)

## YAGI_WILK_B (1)
- Piazzola 1 di TP_WILK_B su B.Cu (-0.08,-5.40) <-> Piazzola 2 di R_WILK_ISO su B.Cu (4.50,-2.53)
