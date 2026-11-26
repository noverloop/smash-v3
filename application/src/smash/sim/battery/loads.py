"""Load sets per mission state — maximalist build (every subsystem fitted).

Each Load carries its basis so the report shows how firm each number is:
  "DS"   datasheet figure;
  "old"  smash-electronics documentation/power_budget.md (2026-07/09);
  "user" figures from the 2026-11-22 transverter power review;
  "est"  engineering estimate — bench-measure before trusting the margin.

Currents are at the load's own rail. PMIC_OUT entries are WATTS (see
power_tree). The S4 transverter (XV_*) and the fins are listed here but
dropped by mission.build_profile unless asked for (xv_tx / fins).
"""
from __future__ import annotations

from smash.sim.battery.power_tree import Load

# ── dormant states (constant current at BAT, closed-form) ─────────────────
I_SHELF_A = 1.0e-6     # old: latch/leakage lump + TMR shelf ear (DS worst cases)
I_STANDBY_A = 9.0e-6   # old: + 3V3_AON (WBA Stop1, TLV3691, Hall arming listener)

# ── Ready (armed hold): MP25 booted then Stop, radar idle, sensors LP ─────
READY = [
    Load("WBA55 Stop1 + AON listeners", "3V3_AON", 8e-6, "old"),
    Load("IMU x3 LP FIFO + H3LIS + mag + temp/power monitors", "3V3", 3.5e-3, "old+est"),
    Load("fin MCU U545 Stop", "3V3", 0.1e-3, "est"),
    Load("LR2021 + XV chain off", "3V3", 0.0, "DS (~uA)"),
    Load("MP25 M33 Stop + A35 retention + PMIC Iq [W]", "PMIC_OUT", 0.038, "old"),
    Load("DDR3L self-refresh [W]", "PMIC_OUT", 0.025, "est (MT41K256M16 IDD6)"),
    Load("AWR1843 idle, image resident: core", "AWR_1V2", 0.15, "old (SWRA689 ~0.22 W device)"),
    Load("AWR1843 idle: 1.8 V", "AWR_1V8", 0.03, "old"),
]

# 1 s once at arming: radar image load + calibration (~2 W at the pack)
RADAR_BOOT_EXTRA = [
    Load("AWR1843 boot: core", "AWR_1V2", 0.35, "old (~2 W pack, 1 s)"),
    Load("AWR1843 boot: RF", "AWR_1V3", 0.50, "old"),
    Load("AWR1843 boot: 1.8 V", "AWR_1V8", 0.10, "old"),
]

# Ready pulse: health-beacon coil, 4 x 47 ohm off BAT_PROT (≈ 0.19 A)
HEALTH_COIL = Load("health coil pulse (4 x 47 R from BAT_PROT)", "BAT", 0.19, "DS (generator)")
HEALTH_COIL_DUTY = 0.03   # est: 3-30 Hz keying, ~1 ms pulses

# ── Descent (drop -> parachute opens): everything running ─────────────────
DESCENT = [
    Load("WBA55 run (BLE)", "3V3_AON", 10e-3, "old"),
    Load("LR2021 IF drive + sensors + MCUs", "3V3", 50e-3, "user"),
    Load("LR2021 TCXO SiT5356 (on with the LR2021 XOSC)", "3V3", 53e-3, "DS Idd max"),
    Load("XV LO ADF4351", "3V3", 125e-3, "user"),
    Load("XV mixer LTC5552", "3V3", 132e-3, "user"),
    Load("XV PA GRF5126 (TX keyed)", "XV_5V", 110e-3, "user / DS"),
    Load("MP25 dual A35 + NPU + M33 run [W]", "PMIC_OUT", 1.60, "old (~420 mA SoC) est"),
    Load("DDR3L active [W]", "PMIC_OUT", 0.30, "est"),
    # (2026-11-23) VB1943 replaces the AR0234: DS14880 Table 23, GS NIR 30 fps
    # 1920x1080 2-lane — VANA 26 mA @ 2.8 V + VDDIO 0.5 mA (PMIC), VCORE
    # 124 mA @ 1.15 V on its own buck
    Load("camera VB1943 VANA + VDDIO [W]", "PMIC_OUT", 0.026 * 2.8 + 0.001, "DS14880 T23"),
    Load("camera VB1943 VCORE", "CAM_VCORE", 0.124, "DS14880 T23"),
    Load("QPD + NAND + misc COMP_3V3 [W]", "PMIC_OUT", 0.05, "old"),
    # SWRS236C Table 6-4: 2TX/4RX, 25 % duty = 1.36 W average at the device
    # terminals (split across the rails est: 0.54 + 0.52 + 0.32 W)
    Load("AWR1843 framing: core", "AWR_1V2", 0.45, "DS T6-4 1.36 W avg, split est"),
    Load("AWR1843 framing: RF (avg)", "AWR_1V3", 0.40, "DS T6-4, split est"),
    Load("AWR1843 framing: 1.8 V", "AWR_1V8", 0.18, "DS T6-4, split est"),
    Load("fins, steering average (4 x TC78H653)", "COMP_5V", 1.0 / 5.03, "est (1 W avg)"),
]

# ms-class peaks on top of DESCENT
# Active part of the frame (~6 ms of chirps): RF rail to 1.5 A of its 2.0 A
# max (SWRS236C Table 6-3: 1.2 V 1.0 A, 1.3 V 2.0 A, 1.8 V 0.85 A max)
RADAR_CHIRP_EXTRA = Load("AWR1843 active frame (RF rail to 1.5 A)", "AWR_1V3", 1.10,
                         "DS T6-3/6-4 est")
FIN_STEP_EXTRA = Load("one fin driver step (~5 W, firmware-staggered)", "COMP_5V", 4.0 / 5.03,
                      "old (5 W/driver) — winding R not in netlist")
# 25 µm × 30 mm nichrome (≈ 67 Ω) at the 11.9 V nominal (DAC mid-scale):
# 0.18 A → 2.1 W; firmware range 0.9–3.8 W (7.9–15.9 V, generator docstring)
CUTTER_V_NOMINAL = 11.9
CUTTER_W_PER_SECTOR = 2.1


def cutter(sectors: int = 1, watts: float = CUTTER_W_PER_SECTOR) -> Load:
    return Load(f"parachute cutter, {sectors} sector(s) x {watts:g} W, ~0.1-0.5 s",
                "ACTIVATE_HV", sectors * watts / CUTTER_V_NOMINAL, "generator docstring")
