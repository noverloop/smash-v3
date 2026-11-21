"""Smash DEVELOPMENT BOARD — the whole tower schematic on ONE flat board.

(2026-11-21, user) Development happens on a flat board, not on the tower. The
dev board carries every tower subsystem (same parts, same nets — one
schematic) on a single rectangular 8L 2+4+2 HDI board (the Speedstack build,
0.868 mm, like the tower tiles), plus a single-USB diagnostic section that also
flashes and diagnoses a TOWER through its aft interface:

  phase 1 (this file so far): the tower schematic retagged onto `dev_board`,
          tower-only parts removed (aft-cap pads, cells), placed + exported.
  phase 2: USB-C → hub (USB2514B) → MP25 USB + STM32G474 (CMSIS-DAP probe,
          consoles, gs_usb CAN, INA228 / INA241 power meter), bus switches
          to the on-board aft fixture, printed slot antennas + u.FL ports.

Run:  python3 generate_devboard.py   → dist/dev_board/
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "application" / "src"))

import generate_stackup as G                                    # noqa: E402

DEV = "dev_board"
OUT = REPO / "dist" / DEV
# Tower builders that make up the maximalist schematic (all payloads).
_BUILDERS = (G.build_qpd_module, G.build_radar_nose_io, G.build_usb_nose,
             G.build_camera_module, G.build_aft_end_board, G.build_activation_interface,
             G.build_radar_module_awr1843aop, G.build_companion_compute,
             G.build_power_board, G.build_wakeup_board, G.build_fins_module)


def remove_component(d, ref: str) -> bool:
    """Drop a chip / battery from the design and strip its pins from every net."""
    hit = False
    for lst in (d.chips, d.batteries):
        for c in list(lst):
            if c.ref == ref:
                lst.remove(c)
                hit = True
    if hit:
        for net in d.nets:
            net.pins[:] = [p for p in net.pins if p[0] != ref]
    return hit


def tower_only_refs(d) -> list:
    """Parts that only exist because of the tower's mechanics: the virtual
    aft_end_cap crown contacts (the dev board reaches its own MCUs directly;
    a TOWER's aft interface is served by the dev board's fixture, phase 2)
    and the primary cells (the dev board runs from USB / bench)."""
    refs = [c.ref for c in d.chips if getattr(c, "board_tag", None) == G.AFT_CAP]
    refs += [b.ref for b in d.batteries]
    return refs


def build_design():
    d = G.Design()
    G._set_battery_mode("maximalist")
    G._prime_power_rails(d)
    for fn in _BUILDERS:
        fn(d)
    removed = [r for r in tower_only_refs(d) if remove_component(d, r)]
    locks = build_diag(d)
    return d, removed, locks


def retag(d) -> None:
    """Every part onto the one flat board (after the schematic is written, so
    the schematic keeps one framed section per tower subsystem)."""
    for c in list(d.chips) + list(d.batteries):
        c.board_tag = DEV


# ══ phase 2: single-USB diagnostic section + tower fixture ═══════════════════
DIAG = "dev_diag"            # schematic section (retagged onto dev_board after)
FIXTURE_CENTRE = (22.0, 0.0)  # aft fixture centre on the dev board (board frame, mm)
# (2026-11-21, user) seating: 3 dowels into the cap's locating holes (uneven
# angles = key), a guide collar (Ø36.2 bore) on 3 M2 screws, and 3 GND contacts
# ~120° apart split off as SEAT sense lines (LED each + G474 input).
# dowels = Mill-Max 5849 locating pins (parts, P_DEV_DOWEL1-3), pinned below
FIXTURE_COLLAR_R_MM, FIXTURE_COLLAR_ANGLES_DEG = 22.5, (0.0, 120.0, 240.0)
FIXTURE_KEEPOUT_R_MM = 25.0       # collar OD
SEAT_TEETH = (19, 43, 56)         # GND teeth at 117° / 261° / 339° (largest gap 144° < 180°)
FIXTURE_R = (15.2, 16.6)      # spring pins staggered radially (6° contact pitch = 1.67 mm)
_AFT_MAP = REPO / "dist" / "maximalist" / "sleeve" / "aft_end_cap" / "aft_end_cap.md"


def aft_contacts() -> list:
    """(tooth, angle_deg, net, label, role) from the tower generator's aft-cap
    contact map (dist/maximalist/sleeve/aft_end_cap/aft_end_cap.md)."""
    import re
    rows = []
    for ln in _AFT_MAP.read_text().splitlines():
        m = re.match(r"\| (\d+) \| ([\d.]+) \| [^|]* \| ([^|]*) \| ([^|]*) \| (\w+) \|", ln)
        if m:
            rows.append((int(m[1]), float(m[2]), m[3].strip(), m[4].strip(), m[5]))
    return rows


def build_diag(d) -> dict:
    """USB-C → ESD → USB2514B hub → (1) MP25 USB, (2) STM32G474 [CMSIS-DAP for
    6 SWD targets, consoles, gs_usb CAN-FD, INA228 / INA241 power meter];
    bus-switched link to a tower through the on-board aft fixture."""
    import math
    from smash.netlist import cap_to_gnd, res_between
    from smash.parts import devboard as DB
    from smash.parts.usb import add_uj20_c_h_g_msmt_1a_p16_tr_67
    from smash.parts.ldos import add_ldl112pv33r
    from smash.parts.oscillators import add_dsc1001ci5_032_0000
    from smash.parts.transceivers import add_tcan1042gvdq1
    from smash.parts.leds import add_ltst_c190gkt, add_ltst_c190krkt
    from smash.parts.mosfets import add_dmp6110svt_7, add_bss138akm_qyl
    from smash.parts.mechanical import add_pogo_pad
    N = lambda name: G._net(d, name)
    T = dict(board_tag=DIAG)
    V3 = "DEV_3V3"
    locks = {}

    # ── USB-C (replaces the USB nose's vertical receptacle) ────────────────
    remove_component(d, "J_USB_C")
    usb = add_uj20_c_h_g_msmt_1a_p16_tr_67(d, ref="J_DEV_USB", **T)
    for pn in ("VBUS", "VBUS__1"):
        N("USB_VBUS").connect(usb.pin(pn))                 # → Q_USB_OR → BAT_PROT (tower path)
    for pn in ("GND", "GND__1", "SHIELD", "SHIELD__1", "SHIELD__2", "SHIELD__3"):
        N("GND").connect(usb.pin(pn))
    N("USB_CC1").connect(usb.pin("CC1")); N("USB_CC2").connect(usb.pin("CC2"))   # Rd 5.1 k exist
    for pn, net in (("DP1", "DEV_USB_UP_P"), ("DP2", "DEV_USB_UP_P"),
                    ("DN1", "DEV_USB_UP_N"), ("DN2", "DEV_USB_UP_N")):
        N(net).connect(usb.pin(pn))
    esd = DB.add_tpd4e05u06dqar(d, ref="U_DEV_ESD", **T)
    N("DEV_USB_UP_P").connect(esd.pin("D1+")); N("DEV_USB_UP_N").connect(esd.pin("D1-"))
    N("DEV_G4_USB_P").connect(esd.pin("D2+")); N("DEV_G4_USB_N").connect(esd.pin("D2-"))
    for pn in ("GND_1", "GND_2"):
        N("GND").connect(esd.pin(pn))

    # ── dev 3.3 V (from USB VBUS: the diag section lives without the DUT) ──
    ldo = add_ldl112pv33r(d, ref="U_DEV_LDO", **T)
    N("USB_VBUS").connect(ldo.pin("VIN")); N(V3).connect(ldo.pin("VOUT"))
    N("USB_VBUS").connect(ldo.pin("EN")); N("GND").connect(ldo.pin("GND"))
    cap_to_gnd(d, "USB_VBUS", "1uF", ref="C_DEV_LDO_IN", **T)
    cap_to_gnd(d, V3, "10uF", ref="C_DEV_LDO_OUT", **T)

    # ── USB2514B hub ───────────────────────────────────────────────────────
    hub = DB.add_usb2514b_i_m2(d, ref="U_DEV_HUB", **T)
    for pn in ("VDD33_1", "VDD33_2", "VDDA33_1", "VDDA33_2", "VDDA33_3", "VDDA33_4"):
        N(V3).connect(hub.pin(pn))
    for k in range(4):
        cap_to_gnd(d, V3, "100nF", ref=f"C_DEV_HUB_{k}", **T)
    N("GND").connect(hub.pin("EP")); N("GND").connect(hub.pin("TEST"))
    N("DEV_USB_UP_P").connect(hub.pin("USBDP_UP")); N("DEV_USB_UP_N").connect(hub.pin("USBDM_UP"))
    N("USB_D_P").connect(hub.pin("USBDP_DN1")); N("USB_D_N").connect(hub.pin("USBDM_DN1"))   # → MP25
    N("DEV_G4_USB_P").connect(hub.pin("USBDP_DN2")); N("DEV_G4_USB_N").connect(hub.pin("USBDM_DN2"))
    for pn in ("USBDP_DN3", "USBDM_DN3", "USBDP_DN4", "USBDM_DN4"):   # DS: both D± high = port off
        N(V3).connect(hub.pin(pn))
    for pn in ("OCS1_N", "OCS2_N", "OCS3_N", "OCS4_N"):
        res_between(d, V3, f"DEV_HUB_{pn}", "10k", ref=f"R_DEV_HUB_{pn}", **T)
        N(f"DEV_HUB_{pn}").connect(hub.pin(pn))
    for pn in ("SDA", "SCL", "HS_IND", "SUSP_IND"):     # default config, bus-powered
        res_between(d, f"DEV_HUB_{pn}", "GND", "10k", ref=f"R_DEV_HUB_{pn}", **T)
        N(f"DEV_HUB_{pn}").connect(hub.pin(pn))
    N("DEV_HUB_CRFILT").connect(hub.pin("CRFILT"))
    cap_to_gnd(d, "DEV_HUB_CRFILT", "1uF", ref="C_DEV_HUB_CRFILT", **T)
    N("DEV_HUB_PLLFILT").connect(hub.pin("PLLFILT"))
    cap_to_gnd(d, "DEV_HUB_PLLFILT", "1uF", ref="C_DEV_HUB_PLLFILT", **T)
    N("DEV_HUB_RBIAS").connect(hub.pin("RBIAS"))
    res_between(d, "DEV_HUB_RBIAS", "GND", "12k", ref="R_DEV_HUB_RBIAS", **T)
    N("DEV_HUB_RESET_N").connect(hub.pin("RESET_N"))
    res_between(d, V3, "DEV_HUB_RESET_N", "10k", ref="R_DEV_HUB_RST", **T)
    cap_to_gnd(d, "DEV_HUB_RESET_N", "100nF", ref="C_DEV_HUB_RST", **T)
    N("DEV_HUB_VBUS_DET").connect(hub.pin("VBUS_DET"))
    res_between(d, "USB_VBUS", "DEV_HUB_VBUS_DET", "47k", ref="R_DEV_HUB_VB1", **T)
    res_between(d, "DEV_HUB_VBUS_DET", "GND", "100k", ref="R_DEV_HUB_VB2", **T)
    osc = add_dsc1001ci5_032_0000(d, ref="Y_DEV_HUB", manf_pn="DSC1001CI5-024.0000",
                                  value="24MHz", name="DSC1001CI5-024.0000", **T)
    for p in osc.pins:
        nm = p.name.upper()
        if "OUT" in nm or "CLK" in nm:
            N("DEV_HUB_CLK").connect(p)
        elif "GND" in nm:
            N("GND").connect(p)
        else:
            N(V3).connect(p)                                # VDD + STDBY/EN
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_HUB_OSC", **T)
    N("DEV_HUB_CLK").connect(hub.pin("XTALIN"))

    # ── STM32G474: probe + consoles + CAN + meter ──────────────────────────
    g = DB.add_stm32g474ceu6(d, ref="U_DEV_G474", **T)
    for pn in ("VDD_1", "VDD_2", "VDD_3", "VDDA", "VREF+", "VBAT"):
        N(V3).connect(g.pin(pn))
    for k in range(4):
        cap_to_gnd(d, V3, "100nF", ref=f"C_DEV_G474_{k}", **T)
    cap_to_gnd(d, V3, "4.7uF", ref="C_DEV_G474_BULK", **T)
    N("GND").connect(g.pin("EP"))
    N("DEV_G4_NRST").connect(g.pin("PG10-NRST"))
    cap_to_gnd(d, "DEV_G4_NRST", "100nF", ref="C_DEV_G474_NRST", **T)
    N("DEV_G4_BOOT0").connect(g.pin("PB8-BOOT0"))                  # ROM DFU over the same USB
    res_between(d, "DEV_G4_BOOT0", "GND", "10k", ref="R_DEV_G474_BOOT0", **T)
    N("DEV_G4_USB_P").connect(g.pin("PA12")); N("DEV_G4_USB_N").connect(g.pin("PA11"))
    pinmap = {
        "PA0": "DEV_ISENSE",          # INA241 → ADC (fast current)
        "PA1": "DEV_TWR_VDD_SENSE",   # tower 3V3_AON present (ADC)
        "PA2": "DEV_BTN_METER",       # meter-reset button
        "PA3": "SWO",                 # USART2_RX ← on-board MP25 SWO
        "PA9": "MP25_CONSOLE_RX",     # USART1_TX → on-board MP25 console
        "PA10": "MP25_CONSOLE_TX",    # USART1_RX ←
        "PA15": "DEV_I2C_SCL", "PB7": "DEV_I2C_SDA",
        "PB12": "DEV_CAN_RX", "PB13": "DEV_CAN_TX",      # FDCAN2
        "PB10": "DEV_TWR_CONS_RX_G", "PB11": "DEV_TWR_CONS_TX_G",   # USART3 ↔ tower console
        "PC11": "DEV_TWR_SWO_G",      # UART4_RX ← tower SWO
        # 6 bit-banged SWD ports (SWDIO, SWCLK, NRST)
        "PA4": "COMP_SWDIO", "PA5": "COMP_SWDCLK", "PA6": "NRST",
        "PA7": "WBA_SWDIO", "PA8": "WBA_SWCLK", "PB0": "WBA_NRST",
        "PB1": "G0B1_FIN_SWDIO", "PB2": "G0B1_FIN_SWCLK", "PB3": "G0B1_FIN_NRST",
        "PB4": "DEV_TWR_MP25_SWDIO_G", "PB5": "DEV_TWR_MP25_SWCLK_G", "PB6": "DEV_TWR_MP25_NRST_G",
        "PB14": "DEV_TWR_WBA_SWDIO_G", "PB15": "DEV_TWR_WBA_SWCLK_G", "PC4": "DEV_TWR_WBA_NRST_G",
        "PC6": "DEV_TWR_FIN_SWDIO_G", "PC10": "DEV_TWR_FIN_SWCLK_G", "PC13": "DEV_TWR_FIN_NRST_G",
        "PF0-OSC_IN": "DEV_TWR_OE_N",        # bus switches (high = isolated)
        "PF1-OSC_OUT": "DEV_TWR_PWR_EN",      # tower supply switch
        "PC14-OSC32_IN": "DEV_LED_ACT", "PC15-OSC32_OUT": "DEV_INA_ALERT_N",
        # seat sense (the G474's own SWD pins — it is flashed by USB DFU)
        "PA13": "TWR_SEAT_1", "PA14": "TWR_SEAT_2", "PB9": "TWR_SEAT_3",
    }
    for pn, net in pinmap.items():
        N(net).connect(g.pin(pn))
    for net in ("DEV_I2C_SCL", "DEV_I2C_SDA", "DEV_INA_ALERT_N"):
        res_between(d, V3, net, "4.7k", ref=f"R_DEV_PU_{net[4:]}", **T)
    res_between(d, V3, "DEV_TWR_OE_N", "10k", ref="R_DEV_TWR_OE", **T)   # isolated by default

    # ── CAN-FD to the tower (gs_usb) ───────────────────────────────────────
    can = add_tcan1042gvdq1(d, ref="U_DEV_CAN", **T)
    N("DEV_CAN_TX").connect(can.pin("TXD")); N("DEV_CAN_RX").connect(can.pin("RXD"))
    N("USB_VBUS").connect(can.pin("VCC")); N(V3).connect(can.pin("VIO"))
    N("GND").connect(can.pin("GND")); N("GND").connect(can.pin("STB"))
    N("TWR_CAN_P").connect(can.pin("CANH")); N("TWR_CAN_N").connect(can.pin("CANL"))
    cap_to_gnd(d, "USB_VBUS", "100nF", ref="C_DEV_CAN_VCC", **T)
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_CAN_VIO", **T)
    res_between(d, "TWR_CAN_P", "TWR_CAN_N", "120", ref="R_DEV_CAN_TERM", **T)

    # ── power meter: bench feed → (shunt) → this board's BAT_RAW and the tower ──
    for ref in ("TP_DEV_BENCH_P", "TP_DEV_BENCH_N"):
        pad = add_pogo_pad(d, ref=ref, manf_pn=None, **T)
        N("DEV_BENCH" if ref.endswith("_P") else "GND").connect(pad.pin("1"))
    meters = (("BAT", "DEV_BENCH", "BAT_RAW", "0x40"),           # this board's battery rail
              ("TWR", "DEV_TWR_FEED", "TWR_BAT_RAW", "0x41"))   # the tower under test
    for tag, hi, lo, _addr in meters:
        res_between(d, hi, lo, "10m", ref=f"R_DEV_SH_{tag}", **T)
        ina = DB.add_ina228aidgsr(d, ref=f"U_DEV_INA_{tag}", **T)
        N(hi).connect(ina.pin("IN+")); N(lo).connect(ina.pin("IN-")); N(lo).connect(ina.pin("VBUS"))
        N(V3).connect(ina.pin("VS")); N("GND").connect(ina.pin("GND"))
        N("DEV_I2C_SCL").connect(ina.pin("SCL")); N("DEV_I2C_SDA").connect(ina.pin("SDA"))
        N("DEV_INA_ALERT_N").connect(ina.pin("ALERT"))
        N("GND").connect(ina.pin("A1"))
        N("GND" if tag == "BAT" else V3).connect(ina.pin("A0"))
        cap_to_gnd(d, V3, "100nF", ref=f"C_DEV_INA_{tag}", **T)
    fast = DB.add_ina241a2idgkr(d, ref="U_DEV_ISENSE", **T)       # fast path on the BAT shunt
    N("DEV_BENCH").connect(fast.pin("IN+")); N("BAT_RAW").connect(fast.pin("IN-"))
    N(V3).connect(fast.pin("VS")); N("GND").connect(fast.pin("GND"))
    N("GND").connect(fast.pin("REF1")); N("GND").connect(fast.pin("REF2"))
    N("DEV_ISENSE").connect(fast.pin("OUT"))
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_ISENSE", **T)
    # tower supply switch (DEV_BENCH → tower), off by default
    qp = add_dmp6110svt_7(d, ref="Q_DEV_TWR_PWR", **T)
    for dp in ("D_1", "D_2", "D_3", "D_4"):
        N("DEV_TWR_FEED").connect(qp.pin(dp))
    N("DEV_BENCH").connect(qp.pin("S")); N("DEV_TWR_PWR_G").connect(qp.pin("G"))
    res_between(d, "DEV_BENCH", "DEV_TWR_PWR_G", "100k", ref="R_DEV_TWR_PWR_H", **T)
    qn = add_bss138akm_qyl(d, ref="Q_DEV_TWR_PWR_LS", **T)
    N("DEV_TWR_PWR_G").connect(qn.pin("3")); N("GND").connect(qn.pin("2"))
    N("DEV_TWR_PWR_EN").connect(qn.pin("1"))
    res_between(d, "DEV_TWR_PWR_EN", "GND", "100k", ref="R_DEV_TWR_PWR_PD", **T)

    # ── bus switches → tower debug lines (enabled only once the tower's VDD is seen) ──
    chans = [("MP25_SWDIO", "SWDIO"), ("MP25_SWCLK", "SWCLK"), ("MP25_NRST", "NRST"),
             ("SWO", "SWO"), ("WBA_SWDIO", "WBA_SWDIO"), ("WBA_SWCLK", "WBA_SWCLK"),
             ("WBA_NRST", "WBA_NRST"), ("FIN_SWDIO", "FIN_SWDIO"), ("FIN_SWCLK", "FIN_SWCLK"),
             ("FIN_NRST", "FIN_NRST"), ("CONS_TX", "CONS_TX"), ("CONS_RX", "CONS_RX")]
    for k, (gname, label) in enumerate(chans):
        sw = k // 4
        if k % 4 == 0:
            bs = DB.add_sn74cb3t3125pwr(d, ref=f"U_DEV_BUSSW{sw}", **T)
            N(V3).connect(bs.pin("VCC")); N("GND").connect(bs.pin("GND"))
            cap_to_gnd(d, V3, "100nF", ref=f"C_DEV_BUSSW{sw}", **T)
        c = k % 4 + 1
        N(f"DEV_TWR_{gname}_G").connect(bs.pin(f"{c}A"))
        N(f"TWR_{label}").connect(bs.pin(f"{c}B"))
        N("DEV_TWR_OE_N").connect(bs.pin(f"{c}~{{OE}}"))
    res_between(d, "TWR_VDD", "DEV_TWR_VDD_SENSE", "10k", ref="R_DEV_TWR_VDD1", **T)
    res_between(d, "DEV_TWR_VDD_SENSE", "GND", "20k", ref="R_DEV_TWR_VDD2", **T)

    # ── aft fixture: one spring pin per tower aft contact (same contact map) ──
    fx, fy = FIXTURE_CENTRE
    to_twr = {"3V3_AON": "TWR_VDD", "BAT_RAW": "TWR_BAT_RAW", "EXT_CAN_P": "TWR_CAN_P",
              "EXT_CAN_N": "TWR_CAN_N", "FLEX_GND": "GND"}
    for tooth, ang, net, label, role in aft_contacts():
        if role in ("screw", "key"):
            continue
        pin = DB.add_mill_max_0906(d, ref=f"P_DEV_FIX_{tooth:02d}", **T)
        if tooth in SEAT_TEETH:                         # GND contact → seat sense line
            net_ = f"TWR_SEAT_{SEAT_TEETH.index(tooth) + 1}"
        else:
            net_ = to_twr.get(net, f"TWR_{label}" if role != "gnd" else "GND")
        N(net_).connect(pin.pin("1"))
        r = FIXTURE_R[tooth % 2]
        a = math.radians(ang)
        locks[pin.ref] = {"position_mm": [round(fx + r * math.cos(a), 4),
                                          round(fy + r * math.sin(a), 4)],
                          "rotation_deg": 0, "face": "top"}
    res_between(d, "DEV_TWR_FEED", "TWR_BAT_RAW", "0", ref="R_DEV_TWR_LINK", **T)  # meter → fixture

    # locating pins (the real fit): into the aft cap's 3 through locating holes
    from smash.export.aft_cap import CAP_LOCATE_R_MM, CAP_LOCATE_ANGLES_DEG
    for k, ang in enumerate(CAP_LOCATE_ANGLES_DEG, 1):
        dw = DB.add_mill_max_5849(d, ref=f"P_DEV_DOWEL{k}", **T)
        N("GND").connect(dw.pin("1"))
        a = math.radians(ang)
        locks[dw.ref] = {"position_mm": [round(fx + CAP_LOCATE_R_MM * math.cos(a), 4),
                                         round(fy + CAP_LOCATE_R_MM * math.sin(a), 4)],
                         "rotation_deg": 0, "face": "top"}

    # seat lines: pull-up + a green LED each (lit = that side touches the
    # tower's GND ring); all three low = seated flat
    for k in (1, 2, 3):
        res_between(d, V3, f"TWR_SEAT_{k}", "10k", ref=f"R_DEV_SEAT{k}", **T)
        led = add_ltst_c190gkt(d, ref=f"D_DEV_SEAT{k}", **T)
        res_between(d, V3, f"D_DEV_SEAT{k}_A", "1k", ref=f"R_DEV_SEAT{k}_LED", **T)
        N(f"D_DEV_SEAT{k}_A").connect(led.pin("A")); N(f"TWR_SEAT_{k}").connect(led.pin("K"))

    # ── buttons ────────────────────────────────────────────────────────────
    btns = (("S_DEV_MP25_RST", "NRST", "GND"), ("S_DEV_WBA_RST", "WBA_NRST", "GND"),
            ("S_DEV_WAKE", "MAG_WAKE_N", "GND"), ("S_DEV_JUMP", "JUMP_PAD", "GND"),
            ("S_DEV_LAUNCH", "DEV_LAUNCH_SW", "3V3"), ("S_DEV_METER", "DEV_BTN_METER", "GND"),
            ("S_DEV_G4_BOOT", "DEV_G4_BOOT0", V3))
    for ref, a_, b_ in btns:
        sw = DB.add_b3u_1000p(d, ref=ref, **T)
        N(a_).connect(sw.pin("K")); N(b_).connect(sw.pin("A"))
    res_between(d, "DEV_LAUNCH_SW", "PIEZO_P", "10k", ref="R_DEV_LAUNCH", **T)   # fakes the piezo
    res_between(d, V3, "DEV_BTN_METER", "10k", ref="R_DEV_BTN_METER", **T)

    # ── LEDs ───────────────────────────────────────────────────────────────
    leds = (("D_DEV_LED_VBUS", "USB_VBUS", "1.5k", add_ltst_c190gkt),
            ("D_DEV_LED_3V3", V3, "1k", add_ltst_c190gkt),
            ("D_DEV_LED_TWR", "TWR_BAT_RAW", "1k", add_ltst_c190gkt),
            ("D_DEV_LED_HV", "ACTIVATE_HV", "10k", add_ltst_c190krkt))
    for ref, net, rv, fn in leds:
        led = fn(d, ref=ref, **T)
        res_between(d, net, f"{ref}_A", rv, ref=f"R_{ref[2:]}", **T)
        N(f"{ref}_A").connect(led.pin("A")); N("GND").connect(led.pin("K"))
    act = add_ltst_c190gkt(d, ref="D_DEV_LED_ACT", **T)
    res_between(d, V3, "D_DEV_LED_ACT_A", "1k", ref="R_DEV_LED_ACT", **T)
    N("D_DEV_LED_ACT_A").connect(act.pin("A")); N("DEV_LED_ACT").connect(act.pin("K"))

    # ── antenna test ports (u.FL) on the tower's slot feeds ────────────────
    for net in ("ANT_HF_S1", "ANT_HF_S4"):
        uf = DB.add_u_fl_r_smt_1(d, ref=f"J_DEV_{net[4:]}", **T)
        N(net).connect(uf.pin("1")); N("GND").connect(uf.pin("2")); N("GND").connect(uf.pin("3"))
    return locks


def build_panel():
    from smash.layout.boards.smash_evb_v1 import build_config_panel, _standardize_board_stackups
    panel, boards = build_config_panel([DEV], straight=True)
    _standardize_board_stackups(boards)                      # 8L Speedstack, 0.868 mm
    # the tower stands on the aft fixture: keep the top face clear under it
    # (Ø35.8 sleeve + 0.6 mm), the locked spring pins excepted
    import math
    fx, fy = FIXTURE_CENTRE
    R = FIXTURE_KEEPOUT_R_MM
    circ = [(fx + R * math.cos(math.radians(k * 10)), fy + R * math.sin(math.radians(k * 10)))
            for k in range(36)]
    from smash.state.board_geometry import Keepout, Hole
    from smash.export.aft_cap import CAP_LOCATE_R_MM, CAP_LOCATE_ANGLES_DEG
    geo = boards[DEV].geometry
    geo.keepouts.append(Keepout(polygon=circ, layers=("F.Cu",), scope="component",
                                tag="aft_fixture"))
    for ang in FIXTURE_COLLAR_ANGLES_DEG:               # guide-collar screws
        a = math.radians(ang)
        geo.holes.append(Hole(position_mm=(fx + FIXTURE_COLLAR_R_MM * math.cos(a),
                                           fy + FIXTURE_COLLAR_R_MM * math.sin(a)),
                              diameter_mm=2.2, plated=False, tag="fixture_collar"))
    for b in boards.values():
        if hasattr(b, "set_fitted_stackup") and not b.is_spacer:
            b.set_fitted_stackup()
    return panel, boards


def place(d, panel, boards, locks=None):
    import smash.layout.placer.orchestrator as O
    O.load_locked_placements = lambda: {}                    # tower locks don't apply here
    from smash.layout.locked import _parse_entry
    locks = {ref: _parse_entry(ref, e) for ref, e in (locks or {}).items()}
    return O.place_design(d, panel, boards, extra_locks=locks or None)


def area_report(d, boards) -> str:
    b = boards[DEV]
    w, h = b.geometry.rect_dimensions
    faces = {"top": 0.0, "bottom": 0.0}
    for p in b.chip_placements:
        fp = getattr(p.item, "footprint", None)
        crt = getattr(fp, "courtyard", None) or []
        if crt:
            xs = [q[0] for q in crt]; ys = [q[1] for q in crt]
            faces[p.face or "top"] += (max(xs) - min(xs)) * (max(ys) - min(ys))
    return (f"{w:g} × {h:g} mm board ({w * h:.0f} mm²/face): top {faces['top']:.0f} mm² "
            f"({100 * faces['top'] / (w * h):.0f} %), bottom {faces['bottom']:.0f} mm² "
            f"({100 * faces['bottom'] / (w * h):.0f} %)")


COLLAR_BORE_D_MM, COLLAR_OD_MM, COLLAR_H_MM, COLLAR_CHAMFER_MM = 36.2, 44.0, 8.0, 2.5


def write_fixture_collar(out_dir) -> pathlib.Path:
    """(2026-11-21, user) plastic GUIDE collar round the aft fixture: Ø36.2
    bore over the Ø35.8 sleeve, a 45° lead-in chamfer on the top inner edge,
    3 counterbored M2 screws at the board's collar holes. It only guides —
    the cap's blind locating holes on the board's dowels give the real fit."""
    import math
    import cadquery as cq
    r_in, r_out, h, c = COLLAR_BORE_D_MM / 2, COLLAR_OD_MM / 2, COLLAR_H_MM, COLLAR_CHAMFER_MM
    prof = [(r_in, 0.0), (r_out, 0.0), (r_out, h), (r_in + c, h), (r_in, h - c)]
    body = (cq.Workplane("XZ").polyline(prof).close().revolve(360.0, (0, 0, 0), (0, 1, 0)))
    for ang in FIXTURE_COLLAR_ANGLES_DEG:
        a = math.radians(ang)
        x, y = FIXTURE_COLLAR_R_MM * math.cos(a), FIXTURE_COLLAR_R_MM * math.sin(a)
        body = body.cut(cq.Workplane("XY").center(x, y).circle(1.1).extrude(h))
        body = body.cut(cq.Workplane("XY").center(x, y).circle(1.9).extrude(1.6)
                        .translate((0, 0, h - 1.6)))
    out = pathlib.Path(out_dir) / "fixture_collar.step"
    cq.exporters.export(body, str(out))
    (pathlib.Path(out_dir) / "fixture_collar.md").write_text(
        "# Dev-board aft-fixture guide collar (generated)\n\n"
        f"Plastic (PEEK / PETG / PA12 print). Bore Ø{COLLAR_BORE_D_MM} over the Ø35.8 sleeve, OD "
        f"Ø{COLLAR_OD_MM}, {COLLAR_H_MM} mm tall, 45° × {COLLAR_CHAMFER_MM} mm lead-in on the top "
        f"inner edge. 3 × M2 counterbored at r {FIXTURE_COLLAR_R_MM} "
        f"({', '.join(f'{a:g}°' for a in FIXTURE_COLLAR_ANGLES_DEG)}) into the board's collar "
        "holes. Guide only: the aft cap's 3 blind Ø1.6 locating holes on the board's Ø1.5 "
        "dowels set the position and rotation.\n\n"
        "Hold-down (user, 2026-11-21): BY HAND while flashing / testing — the 57 spring pins "
        "push back ~25-45 N (a firm 3-5 kg press); the three SEAT LEDs (D_DEV_SEAT1-3) all lit "
        "= seated flat, and the firmware waits for all three before powering the tower.\n")
    return out


def main() -> int:
    d, removed, locks = build_design()
    print(f"dev board: {len(d.chips)} parts; removed {len(removed)} tower-only parts")
    import shutil
    shutil.rmtree(OUT, ignore_errors=True)               # old split schematic/ folder etc.
    OUT.mkdir(parents=True, exist_ok=True)
    # the schematic keeps one framed section per tower subsystem (+ dev_diag)
    section = {c.ref: c.board_tag for c in list(d.chips) + list(d.batteries)}
    retag(d)
    panel, boards = build_panel()
    print(f"  board thickness {boards[DEV].thickness_mm:.3f} mm "
          f"({boards[DEV].copper_layers} layers)")
    rep = place(d, panel, boards, locks)
    print("  " + area_report(d, boards))
    if rep.any_overflow:
        over = [s for s in rep.per_board if s.overflow]
        print(f"  WARNING: placement overflow: {over}")
    # ONE KiCad project: dev_board.kicad_pro → .kicad_pcb + .kicad_sch, every
    # footprint linked to its symbol (same route as the tower's stackup project)
    import smash.export.kicad_sch as KS
    pcb = OUT / f"{DEV}.kicad_pcb"
    refs = KS.panel_footprint_refs(panel, boards)
    r = G.write_kicad_panel(d, panel, boards, pcb, link_schematic=set(refs))
    G.write_blank_drawing_sheet(pcb)
    _orig = KS.panel_footprint_refs
    KS.panel_footprint_refs = lambda *_a, **_k: {ref: section.get(ref, DEV) for ref in refs}
    try:
        sch = KS.write_panel_schematic(d, panel, boards, OUT, project=DEV)
    finally:
        KS.panel_footprint_refs = _orig
    try:
        cli = G.find_kicad_cli()
        G.relink_multi_unit_footprints(pcb, OUT / f"{DEV}.kicad_sch", cli)
    except G.KiCadCliNotFound:
        pass
    from smash.export.portable_project import write_portable_project
    pp = write_portable_project(pcb)
    write_fixture_collar(OUT)
    print(f"  → {pcb} ({r.get('n_footprints', '?')} footprints) + {DEV}.kicad_sch "
          f"({sch.get('n_parts', '?')} parts, {sch.get('n_symbols', '?')} symbols) — one project; "
          f"portable: {pp['n_footprints']} footprints, {pp['n_models']} 3D models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
