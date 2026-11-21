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
    # (2026-11-21) the aft-cap contacts stay until the lanes are assigned: their
    # nets (SWD, consoles, ...) then get their sleeve lanes + castellations as in
    # the tower — on the dev board the PROGRAMMER is the aft cap (bus → strip)
    global _AFT_CAP_REFS
    _AFT_CAP_REFS = [c.ref for c in d.chips if getattr(c, "board_tag", None) == G.AFT_CAP]
    removed = [b.ref for b in list(d.batteries) if remove_component(d, b.ref)]
    locks = build_diag(d)
    return d, removed, locks


_AFT_CAP_REFS: list = []


def drop_aft_cap(d) -> list:
    """After the lane assignment: the virtual aft-cap contacts go, and the
    tower's mechanical spacer scaffolds (SP_*, "no signals") that the tower
    placement adds — they have no tile on the dev board."""
    sp = [c.ref for c in d.chips if c.ref.startswith("SP_")]
    return [r for r in _AFT_CAP_REFS + sp if remove_component(d, r)]


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
        "PA15": "DEV_I2C_SCL", "PB7": "DEV_I2C_SDA",
        "PB12": "DEV_CAN_RX", "PB13": "DEV_CAN_TX",      # FDCAN2
        "PB10": "DEV_TWR_CONS_RX_G", "PB11": "DEV_TWR_CONS_TX_G",   # USART3 ↔ tower console
        "PC11": "DEV_TWR_SWO_G",      # UART4_RX ← tower SWO
        # (2026-11-21) ONE set of tower ports: bank A → socket, bank B → the flat
        # tower through the sleeve channel; the seat lines pick (firmware)
        "PA4": "DEV_FLAT_EN",         # bank B (flat tower) request — gated by the seat interlock
        "PA5": "DEV_FLAT_PWR_EN",     # flat-tower supply switch
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
    res_between(d, V3, "DEV_FLAT_OE_N", "10k", ref="R_DEV_FLAT_OE", **T)
    res_between(d, "DEV_FLAT_EN", "GND", "100k", ref="R_DEV_FLAT_EN_PD", **T)

    def seat_interlock(top_net, tag):
        """HARDWARE INTERLOCK (2026-11-21, user): top_net → GND only through
        three series NMOS gated by the seat lines. A seat tooth grounds its
        line, so ANY tooth touching (tower seated, even partly) opens the
        chain whatever the firmware does: the flat tower stays isolated."""
        node = top_net
        for k in (1, 2, 3):
            q = add_bss138akm_qyl(d, ref=f"Q_DEV_ILK_{tag}{k}", **T)
            nxt = "GND" if k == 3 else f"DEV_ILK_{tag}{k}"
            N(node).connect(q.pin("3")); N(f"TWR_SEAT_{k}").connect(q.pin("1"))
            N(nxt).connect(q.pin("2"))
            node = nxt

    q_en = add_bss138akm_qyl(d, ref="Q_DEV_FLAT_OE", **T)     # bank B /OE low = on
    N("DEV_FLAT_OE_N").connect(q_en.pin("3")); N("DEV_FLAT_EN").connect(q_en.pin("1"))
    N("DEV_FLAT_OE_SRC").connect(q_en.pin("2"))
    seat_interlock("DEV_FLAT_OE_SRC", "OE")

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
    # one metered feed (bench → 10 mΩ shunt → DEV_FEED), switched to the
    # SOCKET (a real tower) or the FLAT tower (the tiles) — never both
    res_between(d, "DEV_BENCH", "DEV_FEED", "10m", ref="R_DEV_SH", **T)
    ina = DB.add_ina228aidgsr(d, ref="U_DEV_INA", **T)
    N("DEV_BENCH").connect(ina.pin("IN+")); N("DEV_FEED").connect(ina.pin("IN-"))
    N("DEV_FEED").connect(ina.pin("VBUS"))
    N(V3).connect(ina.pin("VS")); N("GND").connect(ina.pin("GND"))
    N("DEV_I2C_SCL").connect(ina.pin("SCL")); N("DEV_I2C_SDA").connect(ina.pin("SDA"))
    N("DEV_INA_ALERT_N").connect(ina.pin("ALERT"))
    N("GND").connect(ina.pin("A1")); N("GND").connect(ina.pin("A0"))
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_INA", **T)
    fast = DB.add_ina241a2idgkr(d, ref="U_DEV_ISENSE", **T)       # fast path, same shunt
    N("DEV_BENCH").connect(fast.pin("IN+")); N("DEV_FEED").connect(fast.pin("IN-"))
    N(V3).connect(fast.pin("VS")); N("GND").connect(fast.pin("GND"))
    N("GND").connect(fast.pin("REF1")); N("GND").connect(fast.pin("REF2"))
    N("DEV_ISENSE").connect(fast.pin("OUT"))
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_ISENSE", **T)
    for tag, out_net, en in (("TWR", "TWR_BAT_RAW", "DEV_TWR_PWR_EN"),
                             ("FLAT", "BAT_RAW", "DEV_FLAT_PWR_EN")):
        qp = add_dmp6110svt_7(d, ref=f"Q_DEV_{tag}_PWR", **T)
        for dp in ("D_1", "D_2", "D_3", "D_4"):
            N(out_net).connect(qp.pin(dp))
        N("DEV_FEED").connect(qp.pin("S")); N(f"DEV_{tag}_PWR_G").connect(qp.pin("G"))
        res_between(d, "DEV_FEED", f"DEV_{tag}_PWR_G", "100k", ref=f"R_DEV_{tag}_PWR_H", **T)
        qn = add_bss138akm_qyl(d, ref=f"Q_DEV_{tag}_PWR_LS", **T)
        src = "GND" if tag == "TWR" else "DEV_FLAT_PWR_SRC"  # flat supply: seat-interlocked
        N(f"DEV_{tag}_PWR_G").connect(qn.pin("3")); N(src).connect(qn.pin("2"))
        N(en).connect(qn.pin("1"))
        res_between(d, en, "GND", "100k", ref=f"R_DEV_{tag}_PWR_PD", **T)
    seat_interlock("DEV_FLAT_PWR_SRC", "PWR")              # flat supply off while seated

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
    # bank B: the same 12 lines to the FLAT tower (through the sleeve channel)
    flat = {"MP25_SWDIO": "COMP_SWDIO", "MP25_SWCLK": "COMP_SWDCLK", "MP25_NRST": "NRST",
            "SWO": "SWO", "WBA_SWDIO": "WBA_SWDIO", "WBA_SWCLK": "WBA_SWCLK",
            "WBA_NRST": "WBA_NRST", "FIN_SWDIO": "G0B1_FIN_SWDIO",
            "FIN_SWCLK": "G0B1_FIN_SWCLK", "FIN_NRST": "G0B1_FIN_NRST",
            "CONS_TX": "MP25_CONSOLE_TX", "CONS_RX": "MP25_CONSOLE_RX"}
    for k, (gname, _label) in enumerate(chans):
        sw = k // 4
        if k % 4 == 0:
            bb = DB.add_sn74cb3t3125pwr(d, ref=f"U_DEV_FLATSW{sw}", **T)
            N(V3).connect(bb.pin("VCC")); N("GND").connect(bb.pin("GND"))
            cap_to_gnd(d, V3, "100nF", ref=f"C_DEV_FLATSW{sw}", **T)
        c = k % 4 + 1
        N(f"DEV_TWR_{gname}_G").connect(bb.pin(f"{c}A"))
        N(flat[gname]).connect(bb.pin(f"{c}B"))
        N("DEV_FLAT_OE_N").connect(bb.pin(f"{c}~{{OE}}"))
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
            ("D_DEV_LED_TWR", "TWR_BAT_RAW", "1k", add_ltst_c190gkt),     # socket powered
            ("D_DEV_LED_FLAT", "BAT_RAW", "1k", add_ltst_c190gkt),        # flat tower powered
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


# ══ (2026-11-21, user) BLOCK layout — no radial packer, nothing on the bottom ══
# One rectangular block per subsystem (the tower boards + dev_diag), every part
# on TOP; the nets that cross subsystems (the tower's sleeve LDS lanes) run in
# a BUS channel through the middle (component keep-out), blocks above / below
# it; the aft fixture sits at the bus's end.
BLOCK_ORDER = ("dev_diag", "usb_nose", "companion_compute", "radar_module",
               "camera_module", "qpd_module", "power_board", "wakeup_board",
               "activation_interface", "aft_end_board")
BUS_H_MM = 8.0                 # bus channel height (routing only)
BLOCK_GAP_MM = 2.0             # between blocks and to the bus
EDGE_MM = 7.0                  # board edge margin (corner mounting holes)
PART_GAP_MM = 0.25             # extra gap between courtyards inside a block
BLOCK_FILL = 0.62              # target courtyard fill inside a block (sets its width)
FIXTURE_BLOCK_MM = 52.0        # the Ø50 collar keep-out + margin


def _crt_box(c):
    fp = getattr(c, "footprint", None)
    pts = (getattr(fp, "courtyard", None) or []) if fp else []
    if not pts:
        w, h = (getattr(c, "size_mm", None) or (1.0, 1.0))
        return w, h, 0.0, 0.0
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys), (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2


def _pack_block(chips):
    """Shelf-pack one subsystem into a near-square block. Returns
    (block_w, block_h, [(ref, x, y)]) with (x, y) the PART origin, block
    lower-left at (0, 0)."""
    import math
    items = sorted(((c.ref, *_crt_box(c)) for c in chips), key=lambda t: (-t[2], -t[1]))
    area = sum((w + PART_GAP_MM) * (h + PART_GAP_MM) for _r, w, h, _x, _y in items)
    width = max(math.sqrt(area / BLOCK_FILL), max((w for _r, w, *_ in items), default=1) + 0.5)
    out, x, y, row_h, used_w = [], 0.0, 0.0, 0.0, 0.0
    for ref, w, h, cx, cy in items:
        if x > 0 and x + w > width:
            x, y, row_h = 0.0, y + row_h + PART_GAP_MM, 0.0
        out.append((ref, x + w / 2 - cx, y + h / 2 - cy))
        x += w + PART_GAP_MM
        row_h = max(row_h, h)
        used_w = max(used_w, x)
    return used_w, y + row_h, out


def block_layout(d, section: dict, fixed: set) -> dict:
    """Positions for every part (board frame, origin = board centre) + the
    board size, fixture centre and bus rectangle."""
    groups = {g: [] for g in BLOCK_ORDER}
    for c in d.chips:
        if c.ref in fixed:
            continue
        groups.setdefault(section.get(c.ref, "dev_diag"), []).append(c)
    blocks = [(g, *_pack_block(cs)) for g, cs in groups.items() if cs]
    # two rows, biggest blocks first onto the shorter row
    rows = {"top": [], "bot": []}
    width = {"top": 0.0, "bot": 0.0}
    for b in sorted(blocks, key=lambda b: -b[1] * b[2]):
        r = min(rows, key=lambda k: width[k])
        rows[r].append(b); width[r] += b[1] + BLOCK_GAP_MM
    row_w = max(width.values())
    top_h = max((b[2] for b in rows["top"]), default=0)
    bot_h = max((b[2] for b in rows["bot"]), default=0)
    W = EDGE_MM * 2 + row_w + FIXTURE_BLOCK_MM
    H = EDGE_MM * 2 + top_h + bot_h + BUS_H_MM + 2 * BLOCK_GAP_MM
    H = max(H, FIXTURE_BLOCK_MM + 2 * EDGE_MM)
    x0 = -W / 2 + EDGE_MM
    pos, rects = {}, {}
    for r, sign in (("top", 1), ("bot", -1)):
        x = x0
        for g, bw, bh, items in rows[r]:
            yb = (BUS_H_MM / 2 + BLOCK_GAP_MM) if sign > 0 else -(BUS_H_MM / 2 + BLOCK_GAP_MM) - bh
            for ref, px, py in items:
                pos[ref] = (round(x + px, 4), round(yb + py, 4))
            rects[g] = (x, yb, x + bw, yb + bh)
            x += bw + BLOCK_GAP_MM
    fixture = (round(x0 + row_w + FIXTURE_BLOCK_MM / 2, 4), 0.0)
    bus = (x0, -BUS_H_MM / 2, x0 + row_w, BUS_H_MM / 2)
    return {"pos": pos, "W": round(W, 1), "H": round(H, 1), "fixture": fixture,
            "bus": bus, "blocks": rects}


# ══ (2026-11-21, user) TILE layout: the tower boards laid flat ═══════════════
# Every tower board appears as a Ø34 TILE at its own placement (the tower's
# placer, locks + castellations: top AND bottom faces exactly as on the tower),
# boxed + titled in silkscreen like the schematic's sections; its castellations
# become plated THROUGH-holes on the tile outline (test points + the joins —
# same net on two tiles = routed). The debug section packs centre-outward on
# the BOTTOM under the tower socket (the spring-pin ring excepted); buttons /
# LEDs on the TOP beside the socket; the USB-C at the board edge.
_OLD_TILE_GRID = (("aft_end_board", "activation_interface", "wakeup_board"),
             ("power_board", "companion_compute", "radar_module"),
             ("camera_module", "qpd_module", "usb_nose"))
# (2026-11-21, user) tiles in STACK ORDER along a straight channel = the LDS
# sleeve unrolled (lanes in sleeve-angle order), alternating above / below it;
# the programming board (socket + debug) is a strip at the channel's aft end
TILE_ORDER = ("aft_end_board", "activation_interface", "wakeup_board", "power_board",
              "companion_compute", "radar_module", "qpd_module", "camera_module", "usb_nose")
TILE_KEY_DEG = 191.25          # the sleeve key / lane gap on every tile (potting hole −56.25°)
PROG_W_MM = 56.0               # programming-board strip (left edge = board edge: USB-C)
CHANNEL_MM = 10.0              # the unrolled sleeve: ~104 lanes on the inner layers
# (2026-11-21, user) 4 tabs, none where the bus crosses: the bus passes a
# fully cut stretch of the slot (|y| ≤ channel/2 + margin stays open)
PROG_SLOT_TABS_Y = (-38.0, -16.0, 16.0, 38.0)
TILE_PITCH_MM = 42.0           # Ø34 tile + castellation fan-out room
TILE_BOX_MM = 38.0             # silkscreen box round each tile
SOCKET_COL_MM = 56.0           # socket column (Ø50 collar + margin)
TILE_EDGE_MM = 6.0
USB_COL_MM = 12.0
PIN_RING_MM = (10.7, 17.7)     # bottom face blocked by the locating + spring pins
TILE_RING_MM = (17.3, 19.0)    # part keep-out ring outside each tile (the rout channel)
ROUT_MM = (17.0, 19.0)         # panel rout slot (inner edge on the castellation centres)
TAB_W_MM = 2.5                 # break-tab width (arc at r 17)
MOUSE_BITE_D_MM, MOUSE_BITES = 0.5, 3


_LANE_CONTRACT: dict = {}


def tower_placements(d) -> dict:
    """Place the design on the REAL tower panel (tower placer + locks +
    castellations) and return {board: [(ref, x, y, rot, face)]}."""
    from smash.layout.placer import place_design
    from smash.layout.placer.spacer_sizing import size_backbone_spacers
    from smash.parts.castellations import place_castellations
    G._empty_aft_end_top(d)
    panel, boards = G.build_panel(straight=G._STRAIGHT_SNAKE, battery_length_mm=G._compartment_mm())
    G.build_spacers(d, boards)
    G._mark_preplace_keepouts(d, boards)
    G._mark_ring_band_keepouts(panel, boards)
    place_design(d, panel, boards)
    G._place_health_coil(d, boards)            # (2026-11-21) embedded beacon coil, as in the tower
    size_backbone_spacers(panel, boards)
    from smash.validators import assert_no_locked_overlaps   # (2026-11-21) as the tower does
    _ov = assert_no_locked_overlaps(boards, accepted=G._ACCEPTED_LOCKED_OVERLAPS)
    if _ov:
        print(f"  WARN: {len(_ov)} packed chip-overlap(s) on the tower boards: {_ov[:5]}")
    global _LANE_CONTRACT
    _LANE_CONTRACT, *_ = place_castellations(d, panel, boards, connect=lambda net, pin: G._net(d, net).connect(pin),
                        cone_exits=G._CONE_EXITS)
    import math
    from smash.parts.castellations import board_fold_transforms, _local_xy
    from smash.export import nose_interface as NI
    fold = board_fold_transforms(panel, list(panel.snake_chain))
    # (2026-11-21, user) the tower's own silk marks: Al / PEEK ring outlines
    # and the slot-antenna "NO COPPER" keep-out sectors
    # the EE reference placements, exactly as the tower export applies them
    G._apply_companion_reference_layout(d, boards)
    G._apply_activation_reference_layout(d, boards)
    G._mark_gap_hardware_silk(panel, boards, fold)
    G._mark_aft_bench_silk(boards)             # (2026-11-21) bench-pad group boxes, as the tower
    out, mech = {}, {}
    for name, b in boards.items():
        if getattr(b, "is_spacer", False):
            continue
        out[name] = [(pl.item.ref, pl.position_mm[0], pl.position_mm[1], pl.rotation_deg,
                      pl.face or "top") for pl in b.chip_placements]
        holes = [(h.position_mm, h.diameter_mm, h.plated, h.tag)
                 for h in (getattr(b.geometry, "holes", None) or [])]
        cast = next((c for c in d.chips if c.ref == f"J_CAST_{name}"), None)
        cast_deg = sorted(math.degrees(math.atan2(p.position_mm[1], p.position_mm[0])) % 360
                          for p in (cast.footprint.pads if cast else []))
        key, key_local = None, NI.KEY_ANGLE_DEG
        if name in fold:                                         # the sleeve key = the lane gap
            lx, ly = _local_xy(fold[name], NI.KEY_ANGLE_DEG, 17.0)
            key_local = math.degrees(math.atan2(ly, lx)) % 360
        if name == NI.HOST and NI.KEY_NOTCH:                     # compute's sleeve-key notch
            key = (key_local, NI.KEY_W_MM, NI.KEY_DEPTH_MM)
        silk = [(o[0], list(o[1]), o[2] if len(o) > 2 else None)
                for o in (getattr(b, "silk_overlays", None) or [])]
        mech[name] = {"holes": holes, "cast_deg": cast_deg, "key": key, "key_local": key_local,
                      "silk": silk}
    return out, mech


def _open_castellation_mask(d) -> None:
    """Castellation pads are mask-tented on the tower (the sleeve via lands in
    the half-barrel); on the dev board they are probe-able through-holes."""
    import dataclasses
    for c in d.chips:
        if c.ref.startswith("J_CAST_") and c.footprint is not None:
            c.footprint.pads[:] = [dataclasses.replace(p, solder_mask_expansion_mm=0.05)
                                   for p in c.footprint.pads]


def _polar_pack(chips, allowed, ring=PIN_RING_MM, step=0.5, gap=0.25):
    """Centre-outward pack of `chips` (bottom face) into the rectangle
    `allowed` (x0, y0, x1, y1, around the socket centre at 0, 0), clear of the
    pin ring. Returns {ref: (x, y)} (part origin) and the refs that did not fit."""
    import numpy as np
    x0, y0, x1, y1 = allowed
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1e-9, step), np.arange(y0, y1 + 1e-9, step))
    cand = np.c_[gx.ravel(), gy.ravel()]
    cand = cand[np.argsort(np.hypot(cand[:, 0], cand[:, 1]))]
    placed, pos, miss = [], {}, []
    for c in sorted(chips, key=lambda c: -(_crt_box(c)[0] * _crt_box(c)[1])):
        w, h, ox, oy = _crt_box(c)
        hw, hh = w / 2 + gap / 2, h / 2 + gap / 2
        cx, cy = cand[:, 0], cand[:, 1]
        ok = (cx - hw >= x0) & (cx + hw <= x1) & (cy - hh >= y0) & (cy + hh <= y1)
        dmin = np.hypot(np.maximum(np.abs(cx) - hw, 0), np.maximum(np.abs(cy) - hh, 0))
        dmax = np.hypot(np.abs(cx) + hw, np.abs(cy) + hh)
        ok &= ~((dmin <= ring[1]) & (dmax >= ring[0]))
        for px, py, phw, phh in placed:
            ok &= ~((np.abs(cx - px) < hw + phw) & (np.abs(cy - py) < hh + phh))
        idx = np.flatnonzero(ok)
        if not len(idx):
            miss.append(c.ref)
            continue
        x, y = cand[idx[0]]
        placed.append((x, y, hw, hh))
        pos[c.ref] = (float(x - ox), float(y - oy))
    return pos, miss


def _shelf(chips, x0, y0, x1, gap=0.6):
    """Simple left-to-right shelves from (x0, y0) downward, width x1 − x0."""
    pos, x, y, row = {}, x0, y0, 0.0
    for c in sorted(chips, key=lambda c: c.ref):
        w, h, ox, oy = _crt_box(c)
        if x > x0 and x + w > x1:
            x, y, row = x0, y - row - gap, 0.0
        pos[c.ref] = (x + w / 2 - ox, y - h / 2 - oy)
        x += w + gap
        row = max(row, h)
    return pos


def tile_layout(d, section: dict, fixture_refs: set) -> dict:
    """Programming strip (left) | channel with the tiles in stack order,
    alternating above / below it, each turned so its lane gap (the sleeve
    key angle) points AWAY from the channel: the castellation ring then
    unrolls onto the channel without crossings."""
    import math
    tiles, mech = tower_placements(d)
    _open_castellation_mask(d)
    P, n = TILE_PITCH_MM, len(TILE_ORDER)
    row_y = CHANNEL_MM / 2 + P / 2
    W = PROG_W_MM + 24.0 + (n - 1) * P / 2 + 23.0
    H = 2 * (row_y + TILE_BOX_MM / 2 + TILE_EDGE_MM)
    xs = -W / 2 + PROG_W_MM + 24.0
    locks, centres = {}, {}
    for k, name in enumerate(TILE_ORDER):
        above = k % 2 == 0
        cx, cy = xs + k * P / 2, (row_y if above else -row_y)
        centres[name] = (cx, cy)
        m = mech.get(name, {})
        # (2026-11-21, user) every tile the SAME way round (potting hole, key and
        # lane gap at one angle) and only quarter turns, so parts stay 0/90/180/270:
        # the boards come in two mirror orientations 180° apart → phi 0 or 180
        phi = 90.0 * round(((TILE_KEY_DEG - m.get("key_local", TILE_KEY_DEG)) % 360) / 90.0) % 360
        c, s_ = math.cos(math.radians(phi)), math.sin(math.radians(phi))
        rot = lambda x, y: (x * c - y * s_, x * s_ + y * c)
        for ref, x, y, r, face in tiles.get(name, []):
            X, Y = rot(x, y)
            locks[ref] = {"position_mm": [round(cx + X, 4), round(cy + Y, 4)],
                          # bottom parts are stored mirrored (mirror_x∘R(θ)): R(φ)∘mirror_x
                          # = mirror_x∘R(−φ), so the stored angle turns the other way
                          "rotation_deg": round((r + (phi if face == "top" else -phi)) % 360, 3),
                          "face": face}
        if m:
            m["holes"] = [(rot(*pos), hd, pl, tg) for pos, hd, pl, tg in m["holes"]]
            m["silk"] = [(ly, [rot(*p) for p in pts], lb) for ly, pts, lb in m.get("silk", [])]
            m["cast_deg"] = sorted((a + phi) % 360 for a in m["cast_deg"])
            if m.get("key"):
                m["key"] = ((m["key"][0] + phi) % 360,) + tuple(m["key"][1:])
    # programming strip: socket at the top, debug below, USB-C on the left edge
    sx, sy = -W / 2 + PROG_W_MM / 2, H / 2 - (FIXTURE_KEEPOUT_R_MM + 1.0)
    fixture = (round(sx, 4), round(sy, 4))
    debug = [c for c in d.chips if section.get(c.ref) == DIAG and c.ref not in fixture_refs
             and c.ref not in locks]
    ui = [c for c in debug if c.ref.startswith(("S_DEV_", "D_DEV_"))]
    usb = [c for c in debug if c.ref == "J_DEV_USB"]
    rest = [c for c in debug if c not in ui and c not in usb]
    ry1 = sy - FIXTURE_KEEPOUT_R_MM - 1.0
    ry0 = -H / 2 + 7.5                                          # above the corner holes
    for c in usb:
        w, h, _ox, _oy = _crt_box(c)
        ux = -W / 2 + 2.0 + h / 2
        locks[c.ref] = {"position_mm": [round(ux, 4), round((ry0 + ry1) / 2, 4)],
                        "rotation_deg": 270, "face": "top"}
        usb_w = h + 3.0
    cx0 = -W / 2 + 1.0 + (usb_w if usb else 0.0)
    cx1 = -W / 2 + PROG_W_MM - 1.5
    top_pos = _shelf(ui, cx0, ry1, cx1)
    used_y = min((y for _x, y in top_pos.values()), default=ry1) - 4.0
    rest_sorted = sorted(rest, key=lambda c: -(_crt_box(c)[0] * _crt_box(c)[1]))
    a_top = (cx1 - cx0) * (used_y - ry0)
    acc, top_set = 0.0, []
    for c in rest_sorted:
        w, h, _ox, _oy = _crt_box(c)
        if acc + (w + 0.6) * (h + 0.6) < 0.55 * a_top:
            top_set.append(c); acc += (w + 0.6) * (h + 0.6)
    bot_set = [c for c in rest_sorted if c not in top_set]
    pos_top = _shelf(top_set, cx0, used_y, cx1)
    pos_bot = _shelf(bot_set, cx0, ry1, cx1)
    for ref, (x, y) in {**top_pos, **pos_top}.items():
        locks[ref] = {"position_mm": [round(x, 4), round(y, 4)], "rotation_deg": 0, "face": "top"}
    for ref, (x, y) in pos_bot.items():
        locks[ref] = {"position_mm": [round(x, 4), round(y, 4)], "rotation_deg": 0, "face": "bottom"}
    miss = [r for r, (x, y) in {**pos_top, **pos_bot}.items()
            if y - _crt_box(next(c for c in rest if c.ref == r))[1] / 2 < ry0 - 0.5]
    return {"locks": locks, "W": round(W, 1), "H": round(H, 1), "fixture": fixture,
            "centres": centres, "miss": miss, "mech": mech,
            "prog_x1": round(-W / 2 + PROG_W_MM, 4)}


def build_panel(layout=None):
    from smash.layout.boards.smash_evb_v1 import build_config_panel, _standardize_board_stackups
    panel, boards = build_config_panel([DEV], straight=True)
    _standardize_board_stackups(boards)                      # 8L Speedstack, 0.868 mm
    # the tower stands on the aft fixture: keep the top face clear under it
    # (Ø35.8 sleeve + 0.6 mm), the locked spring pins excepted
    import math
    fx, fy = layout["fixture"] if layout else FIXTURE_CENTRE
    if layout:                                           # board sized to the blocks
        g0 = boards[DEV].geometry
        g0.rect_dimensions = (layout["W"], layout["H"])
        g0.holes[:] = [h for h in g0.holes if h.tag != "mount"]
        from smash.state.board_geometry import Hole as _H, Keepout as _K
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (layout["W"] / 2 - 3.5), sy * (layout["H"] / 2 - 3.5)
                g0.holes.append(_H(position_mm=(x, y), diameter_mm=3.2, plated=False, tag="mount"))
        W, H, px = layout["W"], layout["H"], layout["prog_x1"]
        for sy_ in (-1, 1):                                  # programming board's own corners
            g0.holes.append(_H(position_mm=(px - 3.5, sy_ * (H / 2 - 3.5)), diameter_mm=3.2,
                               plated=False, tag="mount"))
        prog = [(-W / 2 + 0.6, -H / 2 + 0.6), (px - 0.6, -H / 2 + 0.6),
                (px - 0.6, H / 2 - 0.6), (-W / 2 + 0.6, H / 2 - 0.6)]
        ch = [(px + 2.5, -CHANNEL_MM / 2), (W / 2 - 3.0, -CHANNEL_MM / 2),
              (W / 2 - 3.0, CHANNEL_MM / 2), (px + 2.5, CHANNEL_MM / 2)]
        for layer in ("F.SilkS", "B.SilkS"):
            boards[DEV].silk_overlays.append((layer, prog, "PROGRAMMER"))
            boards[DEV].silk_overlays.append((layer, ch, "LDS SLEEVE (unrolled)"))
        g0.keepouts.append(_K(polygon=ch, layers=("*.Cu",), scope="component", tag="sleeve_channel",
                              note="the unrolled LDS sleeve: lane bus only, in sleeve-angle order"))
        for name, (cx, cy) in layout.get("centres", {}).items():   # schematic-like boxes
            h = TILE_BOX_MM / 2
            box = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
            circ = [(cx + 17.0 * math.cos(math.radians(k * 5)), cy + 17.0 * math.sin(math.radians(k * 5)))
                    for k in range(72)]                         # the Ø34 tower-board outline
            for layer in ("F.SilkS", "B.SilkS"):
                boards[DEV].silk_overlays.append((layer, box, name))
                boards[DEV].silk_overlays.append((layer, circ, None))
            m = layout.get("mech", {}).get(name, {})
            for ly, pts, lb in m.get("silk", []):                 # ring outlines, ANT keep-outs
                boards[DEV].silk_overlays.append((ly, [(cx + x, cy + y) for x, y in pts], lb))
            for (hx, hy), hd, plated, tag in m.get("holes", []):  # the tower board's holes
                g0.holes.append(_H(position_mm=(cx + hx, cy + hy), diameter_mm=hd,
                                   plated=plated, tag=f"{name}_{tag}"))
            for k in range(36):                                   # ring keep-out (parts)
                a0, a1 = math.radians(k * 10), math.radians(k * 10 + 10)
                r0, r1 = TILE_RING_MM
                g0.keepouts.append(_K(polygon=[(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0)),
                                               (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0)),
                                               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1)),
                                               (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1))],
                                      layers=("*.Cu",), scope="component", tag="tile_ring",
                                      note="rout ring: no parts; only castellation escapes cross it"))
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


def _fp_npth(ref, x, y, d, seed):
    import uuid
    u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/{seed}")
    return (f'\t(footprint "smash_mech:mouse_bite"\n\t\t(layer "F.Cu")\n\t\t(uuid "{u}")\n'
            f'\t\t(at {x:.4f} {y:.4f})\n'
            f'\t\t(attr board_only exclude_from_pos_files exclude_from_bom allow_missing_courtyard)\n'
            f'\t\t(property "Reference" "{ref}" (at 0 0 0) (layer "F.SilkS") (hide yes)\n'
            f'\t\t\t(effects (font (size 0.5 0.5) (thickness 0.1))))\n'
            f'\t\t(pad "" np_thru_hole circle (at 0 0) (size {d} {d}) (drill {d}) '
            f'(layers "*.Cu" "*.Mask"))\n\t)')


def _fp_fiducial(ref, x, y, bottom, seed):
    import uuid
    u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/{seed}")
    cu, mask = ("B.Cu", "B.Mask") if bottom else ("F.Cu", "F.Mask")
    return (f'\t(footprint "smash_mech:fiducial"\n\t\t(layer "{cu}")\n\t\t(uuid "{u}")\n'
            f'\t\t(at {x:.4f} {y:.4f})\n'
            f'\t\t(attr smd board_only exclude_from_bom allow_missing_courtyard)\n'
            f'\t\t(property "Reference" "{ref}" (at 0 0 0) (layer "{"B" if bottom else "F"}.SilkS") (hide yes)\n'
            f'\t\t\t(effects (font (size 0.5 0.5) (thickness 0.1))))\n'
            f'\t\t(pad "1" smd circle (at 0 0) (size 1 1) (layers "{cu}" "{mask}") '
            f'(solder_mask_margin 1.0))\n\t)')


def _tabs(cast_deg, key, n=3):
    """Tab centre angles: the widest castellation-free gaps, ≥ 90° apart."""
    pts = sorted(set(round(a, 3) for a in cast_deg)) or [0.0]
    gaps = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)] + (360 if i + 1 == len(pts) else 0)
        mid = ((a + b) / 2) % 360
        if key and min(abs(mid - key[0]), 360 - abs(mid - key[0])) < 15:
            continue
        gaps.append((b - a, mid))
    out = []
    for w, mid in sorted(gaps, reverse=True):
        if all(min(abs(mid - o[0]), 360 - abs(mid - o[0])) >= 90 for o in out):
            out.append((mid, w))
        if len(out) == n:
            break
    return out


LDS_STUB_R_MM = ROUT_MM[1] + 0.6      # stubs end just outside the cut line
LDS_STUB_W_MM = 0.10                  # = the HDI min track (Default netclass)


def add_lds_stubs(pcb) -> int:
    """(2026-11-21, user) Pre-routed LDS escapes on copper, in BOTH files:
    a straight radial F.Cu stub from every castellation pad out across the
    tile ring to r 19.6 (past the cut line). The layout EE continues them into
    the channel bus on the dev board; on the production panel the slot cuts
    each stub at its own pad (= the castellated half-hole)."""
    import math, re, uuid
    txt = pcb.read_text()
    segs = []
    for m in re.finditer(r'"Reference" "(J_CAST_\w+)"', txt):
        head = txt.rfind("\n\t(footprint", 0, m.start())
        end = txt.find("\n\t(footprint", m.start())
        end = len(txt) if end < 0 else end
        blk = txt[head:end]
        fx, fy, *fr = map(float, re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', blk)
                          .groups(default="0"))
        th = math.radians(fr[0] if fr else 0.0)
        for pm in re.finditer(r'\(pad "([^"]*)" thru_hole.*?\(at ([-\d.]+) ([-\d.]+)[^)]*\).*?'
                              r'\(net "([^"]+)"\)', blk, re.S):
            net = pm[4]
            if net.startswith("unconnected"):
                continue
            px, py = float(pm[2]), float(pm[3])
            x = fx + px * math.cos(th) + py * math.sin(th)        # KiCad: y down, CCW angles
            y = fy - px * math.sin(th) + py * math.cos(th)
            r = math.hypot(x - fx, y - fy)
            if not 16.0 < r < 18.0:
                continue
            ux, uy = (x - fx) / r, (y - fy) / r
            ex, ey = fx + ux * LDS_STUB_R_MM, fy + uy * LDS_STUB_R_MM
            u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/lds/{m[1]}/{pm[1]}")
            segs.append(f'\t(segment\n\t\t(start {x:.4f} {y:.4f})\n\t\t(end {ex:.4f} {ey:.4f})\n'
                        f'\t\t(width {LDS_STUB_W_MM})\n\t\t(layer "F.Cu")\n\t\t(net "{net}")\n'
                        f'\t\t(uuid "{u}")\n\t)')
    end = txt.rstrip().rfind(")")
    pcb.write_text(txt[:end] + "\n".join(segs) + "\n" + txt[end:])
    return len(segs)


# (2026-11-21, user: "too close") lanes round-robin over 4 inner layers:
# 0.40 mm pitch per layer = 0.30 mm gaps (4x the 0.075 min), and a track on one
# layer sits over a 0.1 mm-offset neighbour, not stacked on another track
BUS_LAYERS = ("In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu")
BUS_SPILL = ("In1.Cu", "In6.Cu")         # a reused angle whose spans would touch
BUS_STEP_MM, BUS_W_MM = 0.10, 0.10


def add_lds_bus(pcb, lay) -> dict:
    """(2026-11-21, user) The LDS bus on copper: the tower sleeve's lane
    contract laid into the channel. One track per lane angle, ACROSS the
    channel in sleeve-angle order, ALONG it from the first to the last tile
    the net connects (tiles sit in stack order, so this is the sleeve
    unrolled); nets the programmer strip also uses run on to the channel's aft
    end. GND lanes are left to the pours. The EE joins each castellation stub
    to its lane with a via."""
    import re, uuid
    txt = pcb.read_text()
    W, H = lay["W"], lay["H"]
    m = re.search(r'\(footprint "[^"]*mech[_:]mount".*?\(at ([-\d.]+) ([-\d.]+)\)', txt, re.S)
    ox, oy = float(m[1]) + (W / 2 - 3.5), float(m[2]) - (H / 2 - 3.5)
    world = lambda x, y: (ox + x, oy - y)
    pad_nets = set(re.findall(r'\(pad "[^"]*" [^\n]*(?:\n[^\n]*){0,8}?\(net "([^"]+)"\)', txt))
    prog_nets = set()
    for fm in re.finditer(r'"Reference" "([A-Z]+_DEV_\w*)"', txt):
        e = txt.find("\n\t(footprint", fm.start())
        prog_nets |= set(re.findall(r'\(net "([^"]+)"\)', txt[fm.start():e if e > 0 else None]))
    cx = {n: c[0] for n, c in lay["centres"].items()}
    x_start = lay["prog_x1"] + 2.5
    lanes = []
    for key, ln in (_LANE_CONTRACT.get("lanes") or {}).items():
        if ln.get("kind") in ("gnd_plane", "crown_payload"):
            continue
        net = ln.get("net", key)
        if net not in pad_nets:
            continue
        xs = [cx[b] for b in ln.get("boards", []) if b in cx]
        if not xs:
            continue
        x0, x1 = min(xs), max(xs)
        if net in prog_nets:
            x0 = x_start
        if x1 - x0 < 1.0:
            continue
        for ang in ln.get("angles", []):
            lanes.append((round(ang % 360, 3), x0, x1, net))
    angles = sorted({a for a, *_ in lanes})
    rank = {a: k for k, a in enumerate(angles)}
    y0 = -(len(angles) - 1) * BUS_STEP_MM / 2
    used, segs, spill = {}, [], 0
    for ang, x0, x1, net in sorted(lanes):
        k = rank[ang]
        layer = BUS_LAYERS[k % len(BUS_LAYERS)]
        if any(not (x1 + 1.0 < a or x0 - 1.0 > b) for a, b in used.get((k, layer), [])):
            layer = BUS_SPILL[k % 2]; spill += 1
        used.setdefault((k, layer), []).append((x0, x1))
        y = y0 + k * BUS_STEP_MM
        (sx, sy), (ex, ey) = world(x0, y), world(x1, y)
        u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/bus/{net}/{ang}")
        segs.append(f'\t(segment\n\t\t(start {sx:.4f} {sy:.4f})\n\t\t(end {ex:.4f} {ey:.4f})\n'
                    f'\t\t(width {BUS_W_MM})\n\t\t(layer "{layer}")\n\t\t(net "{net}")\n'
                    f'\t\t(uuid "{u}")\n\t)')
    end = txt.rstrip().rfind(")")
    pcb.write_text(txt[:end] + "\n".join(segs) + "\n" + txt[end:])
    return {"tracks": len(segs), "angles": len(angles), "spill": spill,
            "width_mm": round((len(angles) - 1) * BUS_STEP_MM + BUS_W_MM, 2),
            "prog": len({n for *_, n in lanes if n in prog_nets})}


def write_panel_variant(pcb, lay) -> dict:
    """Fiducials on the dev board, and dev_board_panel.kicad_pcb: the same
    board + a 2 mm rout slot round every tile (inner edge on the castellation
    centres → castellated half-holes), 3 break tabs with mouse bites at the
    widest castellation-free gaps, compute's key notch in its slot."""
    import math, re
    from shapely.geometry import Point, Polygon, box
    from shapely import affinity
    txt = pcb.read_text()
    W, H = lay["W"], lay["H"]
    m = re.search(r'\(footprint "[^"]*mech[_:]mount".*?\(at ([-\d.]+) ([-\d.]+)\)', txt, re.S)
    lx, ly = -(W / 2 - 3.5), -(H / 2 - 3.5)              # the first mount hole (sx = sy = −1)
    ox, oy = float(m[1]) - lx, float(m[2]) + ly
    world = lambda x, y: (ox + x, oy - y)
    fids = [(-W / 2 + 10, H / 2 - 3.0), (W / 2 - 10, H / 2 - 3.0), (-W / 2 + 10, -H / 2 + 3.0)]
    fid_txt = [_fp_fiducial(f"FID{k + 1 + 3 * bot}", *world(x, y), bot, f"fid{k}{bot}")
               for bot in (0, 1) for k, (x, y) in enumerate(fids)]
    # (2026-11-21, user) LOCAL fiducials: 3 per tile square (box corners, outside
    # the rout ring, asymmetric) and 3 on the programmer strip, both faces
    c = TILE_BOX_MM / 2 - 1.5
    local = {name: [(cx - c, cy + c), (cx + c, cy + c), (cx - c, cy - c)]
             for name, (cx, cy) in lay["centres"].items()}
    px = lay["prog_x1"]
    local["programmer"] = [(-W / 2 + 4.0, -H / 2 + 12.0), (px - 4.0, -H / 2 + 12.0),
                           (px - 4.0, H / 2 - 10.0)]
    for name, pts in local.items():
        for bot in (0, 1):
            for k, (x, y) in enumerate(pts):
                fid_txt.append(_fp_fiducial(f"FID_{name}_{'B' if bot else 'T'}{k + 1}",
                                            *world(x, y), bot, f"lfid/{name}/{k}{bot}"))
    end = txt.rstrip().rfind(")")
    dev_txt = txt[:end] + "\n".join(fid_txt) + "\n" + txt[end:]
    pcb.write_text(dev_txt)
    from shapely.ops import unary_union
    polys, bites, ntab, slots = [], [], 0, []
    px = lay["prog_x1"]
    pslot = box(px, -H / 2 - 1, px + ROUT_MM[1] - ROUT_MM[0], H / 2 + 1)
    for ty in PROG_SLOT_TABS_Y:                              # programming board break tabs
        pslot = pslot.difference(box(px - 1, ty - TAB_W_MM / 2, px + 3, ty + TAB_W_MM / 2))
        for k in range(MOUSE_BITES):
            bites.append(world(px + 1.0, ty + (k - (MOUSE_BITES - 1) / 2) * 0.8))
        ntab += 1
    slots.append(pslot)
    for name, (cx, cy) in lay["centres"].items():
        mm = lay["mech"].get(name, {})
        key = mm.get("key")
        ring = Point(0, 0).buffer(ROUT_MM[1], 180).difference(Point(0, 0).buffer(ROUT_MM[0], 180))
        if key:                                           # compute's key notch joins the slot
            ka, kw, kd = key
            notch = affinity.rotate(box(ROUT_MM[0] - kd, -kw / 2, ROUT_MM[0] + 0.1, kw / 2), ka,
                                    origin=(0, 0))
            ring = ring.union(notch)
        tabs = _tabs(mm.get("cast_deg", []), key)
        for t, gap_deg in tabs:
            # tab + bites fit the castellation-free gap (pad Ø ~0.6 + 0.3 mask margin each side)
            free = math.radians(gap_deg) * ROUT_MM[0] - 1.2
            tab_w = max(0.8, min(TAB_W_MM, free))
            hw = math.degrees(tab_w / 2 / ROUT_MM[0])
            wedge = Polygon([(0, 0)] + [(30 * math.cos(math.radians(t + a)),
                                         30 * math.sin(math.radians(t + a)))
                                        for a in (-hw, 0, hw)])
            ring = ring.difference(wedge)
            nb = max(1, min(MOUSE_BITES, int((tab_w - MOUSE_BITE_D_MM) / 0.8) + 1))
            for k in range(nb):                           # perforation on the cut line
                a = math.radians(t + (k - (nb - 1) / 2) * math.degrees(0.8 / ROUT_MM[0]))
                bites.append(world(cx + ROUT_MM[0] * math.cos(a), cy + ROUT_MM[0] * math.sin(a)))
            ntab += 1
        slots.append(affinity.translate(ring, cx, cy))
    outline = box(-W / 2, -H / 2, W / 2, H / 2).difference(unary_union(slots)).simplify(0.01)
    for g in getattr(outline, "geoms", [outline]):
        for ringc in [g.exterior] + list(g.interiors):
            polys.append([world(x, y) for x, y in list(ringc.coords)[:-1]])
    import uuid
    rout = []
    for i, pts in enumerate(polys):
        u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/rout{i}")
        pl = " ".join(f"(xy {x:.4f} {y:.4f})" for x, y in pts)
        rout.append(f'\t(gr_poly\n\t\t(pts {pl})\n\t\t(stroke (width 0.05) (type solid))\n'
                    f'\t\t(fill none)\n\t\t(layer "Edge.Cuts")\n\t\t(uuid "{u}")\n\t)')
    bite_txt = [_fp_npth(f"MB{k + 1}", x, y, MOUSE_BITE_D_MM, f"mb{k}") for k, (x, y) in enumerate(bites)]
    # (2026-11-21, user) ONE design file: the production cut + drill live on
    # Eco1.User, renamed "Production.Rout"; the fab export applies them or not
    pdir = pcb.parent
    for old in (pdir / f"{DEV}_panel.kicad_pcb", pdir / f"{DEV}_panel.kicad_pro"):
        old.unlink(missing_ok=True)
    marks = [r.replace('(layer "Edge.Cuts")', f'(layer "{PROD_LAYER}")') for r in rout]
    for k, (x, y) in enumerate(bites):
        u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/mbmark{k}")
        marks.append(f'\t(gr_circle\n\t\t(center {x:.4f} {y:.4f})\n'
                     f'\t\t(end {x + MOUSE_BITE_D_MM / 2:.4f} {y:.4f})\n'
                     f'\t\t(stroke (width 0.02) (type solid))\n\t\t(fill yes)\n'
                     f'\t\t(layer "{PROD_LAYER}")\n\t\t(uuid "{u}")\n\t)')
    dev_txt = dev_txt.replace('(21 "Eco1.User" user "User.Eco1")',
                              f'(21 "{PROD_LAYER}" user "Production.Rout")')
    e2 = dev_txt.rstrip().rfind(")")
    pcb.write_text(dev_txt[:e2] + "\n".join(marks) + "\n" + dev_txt[e2:])
    pan_txt = re.sub(r'\t\(gr_line\s*\(start [^)]*\)\s*\(end [^)]*\)\s*\(stroke [^\n]*\)\s*'
                     r'\(layer "Edge\.Cuts"\)\s*\(uuid "[^"]*"\)\s*\)\n', "", dev_txt)
    end = pan_txt.rstrip().rfind(")")
    fab = write_fab_sets(pcb, pan_txt[:end] + "\n".join(rout + bite_txt) + "\n" + pan_txt[end:])
    (pdir / "PANEL_NOTES.md").write_text(
        "# Dev board / production panel (generated)\\n\\n"
        "ONE design file, dev_board.kicad_pcb. Layer Eco1.User is named Production.Rout: "
        "the rout slots round each Ø34 tower tile + beside the programmer strip, and the "
        "mouse-bite drills. Fab sets: fab/dev = the board as drawn (outline routed); "
        "fab/production = the same + Production.Rout applied (slots → Edge.Cuts, bites → "
        "NPTH drill). Nothing else differs.\\n\\n"
        f"- Rout: {ROUT_MM[1] - ROUT_MM[0]:g} mm slot, inner edge at r {ROUT_MM[0]:g} = through the "
        "castellation hole centres → CASTELLATED (plated half) holes: call this out to the fab "
        "(castellation process: plate, then rout).\\n"
        f"- {ntab} break tabs ({TAB_W_MM:g} mm) at the widest castellation-free gaps, "
        f"{MOUSE_BITES} × Ø{MOUSE_BITE_D_MM:g} mouse bites each, on the cut line.\\n"
        "- companion_compute: the sleeve-key notch is part of its slot.\\n"
        "- PROGRAMMER strip (socket + debug, USB-C on the panel edge): 2 mm slot on its "
        f"channel side, {len(PROG_SLOT_TABS_Y)} tabs; with its corner holes it is a stand-alone "
        "tower programmer.\\n"
        "- Traces that cross a slot (castellation escapes, the programmer→channel bus) are "
        "milled through: they only matter on the uncut dev board (dev_board.kicad_pcb).\\n"
        "- ROUTING RULE (both files): a trace may cross a tile's ring ONLY as a straight "
        "radial stub from its own castellation pad (the cut then lands on the pad = the "
        "intended half-hole); never route along or through the ring, and never through a "
        "tab (tabs sit in castellation-free gaps and carry no signals).\\n"
        "- Copper outside the tiles (inter-tile joins, socket, debug) is scrap after depaneling; "
        "nothing inside a tile depends on it. The camera's 0.5 mm Al spreader is bonded after.\\n"
        "- 3 fiducials per side (FID1-3 top, FID4-6 bottom), asymmetric.\\n")
    return {"n_slots": len(polys), "n_tabs": ntab, "n_bites": len(bites), "fab": fab}


PROD_LAYER = "Eco1.User"
FAB_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu",
              "F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "Edge.Cuts")


def write_fab_sets(pcb, production_txt) -> dict:
    """fab/dev and fab/production Gerbers + Excellon from the ONE design file;
    production is derived in a temp file (Production.Rout applied), exported,
    then deleted — it is never a second design file."""
    import subprocess, tempfile
    try:
        cli = G.find_kicad_cli()
    except G.KiCadCliNotFound:
        return {}
    out = {}
    with tempfile.TemporaryDirectory() as td:
        prod = pathlib.Path(td) / f"{DEV}.kicad_pcb"
        prod.write_text(production_txt)
        for mode, src in (("dev", pcb), ("production", prod)):
            d = pcb.parent / "fab" / mode
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(cli), "pcb", "export", "gerbers", "--layers", ",".join(FAB_LAYERS),
                            "-o", str(d) + "/", str(src)], check=True, capture_output=True)
            subprocess.run([str(cli), "pcb", "export", "drill", "--excellon-separate-th",
                            "-o", str(d) + "/", str(src)], check=True, capture_output=True)
            out[mode] = d
    return out


def main() -> int:
    d, removed, locks = build_design()
    print(f"dev board: {len(d.chips)} parts; removed {len(removed)} tower-only parts")
    import shutil
    shutil.rmtree(OUT, ignore_errors=True)               # old split schematic/ folder etc.
    OUT.mkdir(parents=True, exist_ok=True)
    # the schematic keeps one framed section per tower subsystem (+ dev_diag)
    section = {c.ref: c.board_tag for c in list(d.chips) + list(d.batteries)}
    lay = tile_layout(d, section, set(locks))
    removed += drop_aft_cap(d)
    section.update({c.ref: c.board_tag for c in d.chips if c.ref.startswith("J_CAST_")})
    dx, dy = lay["fixture"][0] - FIXTURE_CENTRE[0], lay["fixture"][1] - FIXTURE_CENTRE[1]
    for e in locks.values():                              # fixture pins move with the fixture
        e["position_mm"] = [round(e["position_mm"][0] + dx, 4), round(e["position_mm"][1] + dy, 4)]
    locks.update(lay["locks"])
    print(f"  tile layout: {lay['W']} × {lay['H']} mm, {len(lay['centres'])} tower tiles + socket"
          + (f"; WARNING {len(lay['miss'])} debug part(s) did not fit under the socket: "
             f"{', '.join(lay['miss'][:8])}" if lay["miss"] else ""))
    retag(d)
    panel, boards = build_panel(lay)
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
    n_stubs = add_lds_stubs(pcb)
    bus = add_lds_bus(pcb, lay)
    pv = write_panel_variant(pcb, lay)          # Production.Rout layer + fab/dev, fab/production
    print(f"  → {pcb} ({r.get('n_footprints', '?')} footprints) + {DEV}.kicad_sch "
          f"({sch.get('n_parts', '?')} parts, {sch.get('n_symbols', '?')} symbols) — one project; "
          f"portable: {pp['n_footprints']} footprints, {pp['n_models']} 3D models")
    print(f"  production cut on layer Production.Rout: {pv['n_slots']} outline rings, "
          f"{pv['n_tabs']} tabs, {pv['n_bites']} mouse bites; 6 fiducials; fab sets: "
          + ", ".join(str(v.relative_to(REPO)) for v in pv.get("fab", {}).values()))
    print(f"  LDS escapes: {n_stubs} radial stubs (castellation → r {LDS_STUB_R_MM:g})")
    import os
    if os.environ.get("SMASH_SKIP_CHECKS") != "1":                 # warnings only
        from smash.export.checks import report as _check_report
        _check_report(pcbs=[pcb], schematics=[OUT / f"{DEV}.kicad_sch"], root=REPO)
    print(f"  LDS bus: {bus['tracks']} tracks on {bus['angles']} lane angles, {bus['width_mm']} mm "
          f"wide ({'/'.join(BUS_LAYERS)}; {bus['spill']} on {'/'.join(BUS_SPILL)}); "
          f"{bus['prog']} nets run on to the programmer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
