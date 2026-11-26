"""Smash DEVELOPMENT BOARD — the whole tower schematic on ONE flat board.

(2026-11-21, user) Development happens on a flat board, not on the tower. The
dev board carries every tower subsystem (same parts, same nets — one
schematic) on a single rectangular 8L 2+4+2 HDI board (the Speedstack build,
0.868 mm, like the tower tiles), plus a single-USB diagnostic section that also
flashes and diagnoses a TOWER through its aft interface:

  phase 1 (this file so far): the tower schematic retagged onto `dev_board`,
          tower-only parts removed (aft-cap pads, cells), placed + exported.
  phase 2: USB-C → STM32U535 (CMSIS-DAP probe,
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
_BUILDERS = (G.build_qpd_module, G.build_radar_nose_io, 
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
    G._protect_external_lines(d)          # same crown ESD arrays + MCU series R as the tower
    from smash.parts.coo import apply_coo
    from smash.parts.orderable import apply_orderable
    apply_orderable(d)                    # (2026-11-22) generic passives → orderable MPNs
    apply_coo(d)                          # (2026-11-21) Mouser origin data
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
# ~120° apart split off as SEAT sense lines (LED each + dev-MCU input).
# dowels = Mill-Max 5849 locating pins (parts, P_DEV_DOWEL1-3), pinned below
FIXTURE_COLLAR_R_MM, FIXTURE_COLLAR_ANGLES_DEG = 22.5, (0.0, 120.0, 240.0)
FIXTURE_KEEPOUT_R_MM = 25.0       # collar OD
def seat_teeth() -> tuple:
    """(2026-11-22) three GND teeth of the LIVE aft contact map, spread so the
    largest angular gap stays < 180° (a tilted tower always lifts one). Was a
    hard-coded (19, 43, 56) — after the lane reassignment 19 = FIN3_AOUT2 and
    56 = 3V3, so the seat pull-ups would have driven tower nets."""
    import itertools
    gnd = [(t, a) for t, a, _n, _l, role in aft_contacts() if role == "gnd"]
    best = None
    for tri in itertools.combinations(gnd, 3):
        ang = sorted(a for _t, a in tri)
        gaps = [ang[1] - ang[0], ang[2] - ang[1], 360 - ang[2] + ang[0]]
        if max(gaps) < 180 and (best is None or max(gaps) < best[0]):
            best = (max(gaps), tuple(sorted(t for t, _a in tri)))
    assert best, "no 3 GND teeth with every gap < 180°"
    return best[1]
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
    """USB-C → ESD → STM32U535 [CMSIS-DAP for
    6 SWD targets, consoles, gs_usb CAN-FD, INA228 / INA241 power meter];
    bus-switched link to a tower through the on-board aft fixture."""
    import math
    from smash.netlist import cap_to_gnd, res_between
    from smash.parts import devboard as DB
    from smash.parts.usb import add_uj20_c_h_g_msmt_1a_p16_tr_67
    from smash.parts.ldos import add_ldl112pv33r
    from smash.parts.oscillators import add_dsc1001ci5_032_0000
    from smash.parts.swaps_2026_11 import (add_tja1462btk_0z, add_usblc6_4sc6, add_ru1j002yntcl,
                                           add_stm32u535cbu6, add_wurth_61304021121,
                                           add_wurth_691137710002, add_pac1941t_1e_4mx)
    from smash.parts.leds import add_ltst_c190gkt, add_ltst_c190krkt
    from smash.parts.mosfets import add_pmpb15xp
    from smash.parts.mechanical import add_pogo_pad
    N = lambda name: G._net(d, name)
    T = dict(board_tag=DIAG)
    V3 = "DEV_3V3"
    locks = {}

    # ── USB-C (replaces the USB nose's vertical receptacle) ────────────────
    remove_component(d, "J_USB_C")
    usb = add_uj20_c_h_g_msmt_1a_p16_tr_67(d, ref="J_DEV_USB", **T)
    for pn in ("VBUS", "VBUS__1"):
        N("DEV_VBUS").connect(usb.pin(pn))                 # programmer supply only (2026-11-23)
    for pn in ("GND", "GND__1", "SHIELD", "SHIELD__1", "SHIELD__2", "SHIELD__3"):
        N("GND").connect(usb.pin(pn))
    N("USB_CC1").connect(usb.pin("CC1")); N("USB_CC2").connect(usb.pin("CC2"))
    for k in (1, 2):                                   # Rd: UFP (sink) → the host turns VBUS on
        res_between(d, f"USB_CC{k}", "GND", "5.1k", ref=f"R_DEV_USB_CC{k}", **T)
    for pn, net in (("DP1", "DEV_USB_UP_P"), ("DP2", "DEV_USB_UP_P"),
                    ("DN1", "DEV_USB_UP_N"), ("DN2", "DEV_USB_UP_N")):
        N(net).connect(usb.pin(pn))
    esd = add_usblc6_4sc6(d, ref="U_DEV_ESD", **T)   # (2026-11-22) TPD4E05U06 (China lots) → USBLC6-4SC6
    N("DEV_USB_UP_P").connect(esd.pin("I/O1")); N("DEV_USB_UP_N").connect(esd.pin("I/O2"))
    N("GND").connect(esd.pin("GND")); N("DEV_VBUS").connect(esd.pin("VBUS"))

    # ── dev 3.3 V (from USB VBUS: the diag section lives without the DUT) ──
    ldo = add_ldl112pv33r(d, ref="U_DEV_LDO", **T)
    N("DEV_VBUS").connect(ldo.pin("VIN")); N(V3).connect(ldo.pin("VOUT"))
    next(n for n in d.nets if n.name == V3).voltage_v = 3.3   # (2026-11-21) for the electrical rules
    for _nm, _v in (("DEV_VBUS", 5.0), (V3, 3.3)):
        _n = next(n for n in d.nets if n.name == _nm)
        _n.kind, _n.voltage_v = "power", _v
    N("DEV_VBUS").connect(ldo.pin("EN")); N("GND").connect(ldo.pin("GND"))
    N("GND").connect(ldo.pin("EP"))                                  # thermal pad
    cap_to_gnd(d, "DEV_VBUS", "1uF", ref="C_DEV_LDO_IN", **T)
    cap_to_gnd(d, V3, "10uF", ref="C_DEV_LDO_OUT", **T)

    # ── STM32U535: probe + consoles + CAN + meter ──────────────────────────
    # (2026-11-22) replaces the STM32G474CEU6 (0 stock, 52 wk; availability/
    # decisions.csv). Same UFQFPN-48 7×7 body, different ball map (CubeMX
    # STM32U535CBUx.xml): USB FS PA11/12 (ROM DFU), FDCAN1 PB8/9, USART1 PA9/10
    # ↔ tower console, LPUART1_RX PA3 ← SWO, ADC1 PA0/PA1, I2C1 PB6/7, LDO VCAP.
    g = add_stm32u535cbu6(d, ref="U_DEV_MCU", **T)
    for pn in ("VDD_1", "VDD_2", "VDD_3", "VDDA", "VBAT"):
        N(V3).connect(g.pin(pn))
    for pn in ("VSS_1", "VSS_2", "VSS_3", "VSSA", "PE"):
        N("GND").connect(g.pin(pn))
    for k in range(4):
        cap_to_gnd(d, V3, "100nF", ref=f"C_DEV_MCU_{k}", **T)
    cap_to_gnd(d, V3, "4.7uF", ref="C_DEV_MCU_BULK", **T)
    N("DEV_MCU_VCAP").connect(g.pin("VCAP"))
    cap_to_gnd(d, "DEV_MCU_VCAP", "4.7uF", ref="C_DEV_MCU_VCAP", pin=g.pin("VCAP"), **T)
    N("DEV_MCU_NRST").connect(g.pin("NRST"))
    cap_to_gnd(d, "DEV_MCU_NRST", "100nF", ref="C_DEV_MCU_NRST", **T)
    N("DEV_MCU_BOOT0").connect(g.pin("PH3-BOOT0"))                  # ROM DFU over the same USB
    res_between(d, "DEV_MCU_BOOT0", "GND", "10k", ref="R_DEV_MCU_BOOT0", **T)
    N("DEV_USB_UP_P").connect(g.pin("PA12")); N("DEV_USB_UP_N").connect(g.pin("PA11"))   # USB FS, straight from the USB-C
    pinmap = {
        "PA0": "DEV_ISENSE",          # INA241 → ADC1_IN5 (fast current)
        "PA1": "DEV_TWR_VDD_SENSE",   # tower 3V3_AON present (ADC1_IN6)
        "PA2": "DEV_BTN_METER",       # meter-reset button
        "PB6": "DEV_I2C_SCL", "PB7": "DEV_I2C_SDA",          # I2C1
        "PB8": "DEV_CAN_RX", "PB9": "DEV_CAN_TX",            # FDCAN1
        "PA10": "DEV_TWR_CONS_TX_G", "PA9": "DEV_TWR_CONS_RX_G",   # USART1: RX ← MP25 TX (CONS_TX), TX → MP25 RX (CONS_RX)
        "PA3": "DEV_TWR_SWO_G",       # LPUART1_RX ← tower SWO
        "PA4": "DEV_FLAT_EN",         # bank B (flat tower) request — gated by the seat interlock
        "PA5": "DEV_FLAT_PWR_EN",     # flat-tower supply switch
        "PB4": "DEV_TWR_MP25_SWDIO_G", "PB5": "DEV_TWR_MP25_SWCLK_G", "PB3": "DEV_TWR_MP25_NRST_G",
        "PB14": "DEV_TWR_WBA_SWDIO_G", "PB15": "DEV_TWR_WBA_SWCLK_G", "PB12": "DEV_TWR_WBA_NRST_G",
        "PA6": "DEV_TWR_FIN_SWDIO_G", "PA7": "DEV_TWR_FIN_SWCLK_G", "PA8": "DEV_TWR_FIN_NRST_G",
        "PH0-OSC_IN": "DEV_TWR_OE_N",        # bus switches (high = isolated)
        "PH1-OSC_OUT": "DEV_TWR_PWR_EN",      # tower supply switch
        "PC14-OSC32_IN": "DEV_LED_ACT", "PC15-OSC32_OUT": "DEV_INA_ALERT_N",
        # seat sense (2026-11-22: moved off PA13/PA14 = the probe's own SWD)
        "PB0": "TWR_SEAT_1", "PB1": "TWR_SEAT_2", "PB2": "TWR_SEAT_3",
        # why a power path dropped: input protection fault, 5.9 V / 4.37 V cut-offs
        "PA15": "DEV_INPROT_FAULT", "PB10": "DEV_OVP", "PC13": "DEV_OVP_FLAT",
        "PA13": "DEV_MCU_SWDIO", "PA14": "DEV_MCU_SWCLK",
    }
    for pn, net in pinmap.items():
        N(net).connect(g.pin(pn))
    # (2026-11-22) SWD pads for the probe MCU itself (CMSIS-DAP / any SWD probe)
    for ref, net in (("TP_DEV_MCU_SWDIO", "DEV_MCU_SWDIO"), ("TP_DEV_MCU_SWCLK", "DEV_MCU_SWCLK"),
                     ("TP_DEV_MCU_NRST", "DEV_MCU_NRST"), ("TP_DEV_MCU_3V3", V3),
                     ("TP_DEV_MCU_GND", "GND")):
        pad = add_pogo_pad(d, ref=ref, manf_pn=None, **T)
        N(net).connect(pad.pin("1"))
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
            q = add_ru1j002yntcl(d, ref=f"Q_DEV_ILK_{tag}{k}", **T)
            nxt = "GND" if k == 3 else f"DEV_ILK_{tag}{k}"
            N(node).connect(q.pin("3")); N(f"TWR_SEAT_{k}").connect(q.pin("1"))
            N(nxt).connect(q.pin("2"))
            node = nxt

    q_en = add_ru1j002yntcl(d, ref="Q_DEV_FLAT_OE", **T)     # bank B /OE low = on
    N("DEV_FLAT_OE_N").connect(q_en.pin("3")); N("DEV_FLAT_EN").connect(q_en.pin("1"))
    N("DEV_FLAT_OE_SRC").connect(q_en.pin("2"))
    seat_interlock("DEV_FLAT_OE_SRC", "OE")

    # ── CAN-FD to the tower (gs_usb) ───────────────────────────────────────
    can = add_tja1462btk_0z(d, ref="U_DEV_CAN", **T)   # (2026-11-22) TCAN1042GVDQ1 (EOL) → TJA1462
    N("DEV_CAN_TX").connect(can.pin("TXD")); N("DEV_CAN_RX").connect(can.pin("RXD"))
    N("DEV_VBUS").connect(can.pin("VCC")); N(V3).connect(can.pin("VIO"))
    N("GND").connect(can.pin("GND")); N("GND").connect(can.pin("STB"))
    N("GND").connect(can.pin("EP"))                                  # HVSON exposed pad
    N("TWR_CAN_P").connect(can.pin("CANH")); N("TWR_CAN_N").connect(can.pin("CANL"))
    cap_to_gnd(d, "DEV_VBUS", "100nF", ref="C_DEV_CAN_VCC", **T)
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_CAN_VIO", **T)
    res_between(d, "TWR_CAN_P", "TWR_CAN_N", "120", ref="R_DEV_CAN_TERM", **T)

    # ── power meter: bench feed → (shunt) → this board's BAT_RAW and the tower ──
    # (2026-11-22, user) a real bench input: Würth 2-pole terminal block (was
    # two pogo test pads). Emulates the cells (≈ 3.0-4.0 V) on the metered path.
    tb = add_wurth_691137710002(d, ref="J_DEV_BENCH", **T)
    N("DEV_BENCH_IN").connect(tb.pin("1")); N("GND").connect(tb.pin("2"))
    # INPUT PROTECTION: LTC4365 + two back-to-back 60 V N-FETs (common source)
    # between the terminal and everything else. Reversed leads (to −40 V) and
    # anything outside ≈ 2.5-6.5 V disconnect in ~1 µs — the P-FET switches and
    # the tower behind them never see it. UV/OV divider 806k / 124k / 76.8k:
    # UV 0.5 V at ≈ 2.5 V, OV 0.5 V at ≈ 6.5 V (the 5.9 V U_DEV_OVP trips first).
    from smash.parts.protection import add_ltc4365its8
    from smash.parts.mosfets import add_dmn6075sq_7
    pc = add_ltc4365its8(d, ref="U_DEV_INPROT", **T)
    qa = add_dmn6075sq_7(d, ref="Q_DEV_INPROT_A", **T)
    qb = add_dmn6075sq_7(d, ref="Q_DEV_INPROT_B", **T)
    N("DEV_BENCH_IN").connect(qa.pin("D")); N("DEV_INPROT_S").connect(qa.pin("S"))
    N("DEV_INPROT_S").connect(qb.pin("S")); N("DEV_BENCH").connect(qb.pin("D"))
    N("DEV_INPROT_G").connect(qa.pin("G")); N("DEV_INPROT_G").connect(qb.pin("G"))
    N("DEV_BENCH_IN").connect(pc.pin("VIN")); N("DEV_BENCH").connect(pc.pin("VOUT"))
    N("DEV_INPROT_G").connect(pc.pin("GATE")); N("GND").connect(pc.pin("GND"))
    res_between(d, "DEV_BENCH_IN", "DEV_INPROT_SHDN", "100k", ref="R_DEV_INPROT_SHDN", **T)   # DS: ≥ 100 k if VIN can go negative
    N("DEV_INPROT_SHDN").connect(pc.pin("SHDN"))
    res_between(d, "DEV_BENCH_IN", "DEV_INPROT_UV", "806k", ref="R_DEV_INPROT_1", **T)
    res_between(d, "DEV_INPROT_UV", "DEV_INPROT_OV", "124k", ref="R_DEV_INPROT_2", **T)
    res_between(d, "DEV_INPROT_OV", "GND", "76.8k", ref="R_DEV_INPROT_3", **T)
    N("DEV_INPROT_UV").connect(pc.pin("UV")); N("DEV_INPROT_OV").connect(pc.pin("OV"))
    N("DEV_INPROT_FAULT").connect(pc.pin("FAULT"))
    res_between(d, V3, "DEV_INPROT_FAULT", "10k", ref="R_DEV_INPROT_FLT", **T)
    led_f = add_ltst_c190krkt(d, ref="D_DEV_LED_INPROT", **T)          # red: input fault (FAULT sinks)
    res_between(d, V3, "D_DEV_LED_INPROT_A", "1k", ref="R_DEV_LED_INPROT", **T)
    N("D_DEV_LED_INPROT_A").connect(led_f.pin("A")); N("DEV_INPROT_FAULT").connect(led_f.pin("K"))
    cap_to_gnd(d, "DEV_BENCH", "47uF", ref="C_DEV_BENCH", **T)        # local reservoir after the protection
    # one metered feed (bench → 10 mΩ shunt → DEV_FEED), switched to the
    # SOCKET (a real tower) or the FLAT tower (the tiles) — never both
    res_between(d, "DEV_BENCH", "DEV_FEED", "10m", ref="R_DEV_SH", manf="Panasonic", manf_pn="ERJ-2LWFR010X",
                description="10 mΩ 1 % 0402 current-sense, 0.2 W", **T)
    # (2026-11-22, round 20) INA228 → PAC1941T-1E/4MX (channel 1 on the shunt;
    # ±100 mV FSR = 10 A at 10 mΩ). ADDRSEL → GND. FIRMWARE: pin 1 powers up as
    # the SLOW input (pulled high here → 8 SPS) until set to ALERT1.
    ina = add_pac1941t_1e_4mx(d, ref="U_DEV_INA", **T)
    N("DEV_BENCH").connect(ina.pin("SENSE1+")); N("DEV_FEED").connect(ina.pin("SENSE1-"))
    N(V3).connect(ina.pin("VDD")); N("GND").connect(ina.pin("GND"))
    N("DEV_I2C_SCL").connect(ina.pin("SCL")); N("DEV_I2C_SDA").connect(ina.pin("SDA"))
    N("DEV_INA_ALERT_N").connect(ina.pin("SLOW/ALERT1"))
    N("GND").connect(ina.pin("ADDRSEL")); N(V3).connect(ina.pin("PWRDN"))
    for pn in ("SENSE2+", "SENSE2-", "SENSE3+", "SENSE3-", "SENSE4+", "SENSE4-", "EP"):
        N("GND").connect(ina.pin(pn))                 # PAC1941-1: unused inputs grounded (DS note 1)
    res_between(d, "DEV_INA_GPIO", "GND", "10k", ref="R_DEV_INA_GPIO", **T)
    N("DEV_INA_GPIO").connect(ina.pin("GPIO/ALERT2"))
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_INA", **T)
    fast = DB.add_ina241a2idgkr(d, ref="U_DEV_ISENSE", **T)       # fast path, same shunt
    N("DEV_BENCH").connect(fast.pin("IN+")); N("DEV_FEED").connect(fast.pin("IN-"))
    N(V3).connect(fast.pin("VS")); N("GND").connect(fast.pin("GND"))
    N("GND").connect(fast.pin("REF1")); N("GND").connect(fast.pin("REF2"))
    N("DEV_ISENSE").connect(fast.pin("OUT"))
    N("GND").connect(fast.pin("4"))                                 # DS Table 5-1: reserved, connect to GND
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_ISENSE", **T)
    # (2026-11-23, user) a REAL tower (cells inside) is fed through its aft
    # EXT POWER contact (→ D_EXT_IN on aft_end → BAT_PROT; its interlock
    # isolates the cells), switched by the probe MCU (DEV_TWR_PWR_EN). Set the
    # bench supply to ≈ 5.6 V for a real tower, 3.0-4.0 V (cell emulation on
    # BAT_RAW) for the flat tower — the two outputs are never on together.
    for tag, out_net, en in (("TWR", "TWR_EXT_VIN", "DEV_TWR_PWR_EN"),
                             ("FLAT", "BAT_RAW", "DEV_FLAT_PWR_EN")):
        # PMPB15XP: logic-level, fully on at the 3.0 V flat feed; V_DS/V_GS ±12 V →
        # bench supply ≤ 10 V (5.6 V tower / 3.0-4.0 V flat)
        qp = add_pmpb15xp(d, ref=f"Q_DEV_{tag}_PWR", **T)
        for dp in ("D_1", "D_2", "D_3", "D_4", "D_5"):
            N(out_net).connect(qp.pin(dp))
        for sp in ("S_1", "S_2"):
            N("DEV_FEED").connect(qp.pin(sp))
        N(f"DEV_{tag}_PWR_G").connect(qp.pin("G"))
        res_between(d, "DEV_FEED", f"DEV_{tag}_PWR_G", "100k", ref=f"R_DEV_{tag}_PWR_H", **T)
        qn = add_ru1j002yntcl(d, ref=f"Q_DEV_{tag}_PWR_LS", **T)
        src = "GND" if tag == "TWR" else "DEV_FLAT_PWR_SRC"  # flat supply: seat-interlocked
        N(f"DEV_{tag}_PWR_GD").connect(qn.pin("3")); N(src).connect(qn.pin("2"))
        # the MCU drives the low-side gate through 1 k so the hardware overrides
        # (seat lines, overvoltage cut-off) can pull it low whatever firmware does
        lsg = f"DEV_{tag}_PWR_LSG"
        N(lsg).connect(qn.pin("1"))
        # soft start: 4.7 k gate drive + 22 nF gate-drain (Miller) → the P-FET
        # ramps the output over ≈ 1 ms instead of µs into the tower's bulk caps
        _gd = f"DEV_{tag}_PWR_GD"
        res_between(d, _gd, f"DEV_{tag}_PWR_G", "4.7k", ref=f"R_DEV_{tag}_PWR_GS", **T)
        cap_to_gnd(d, f"DEV_{tag}_PWR_G", "22nF", gnd_net=out_net, ref=f"C_DEV_{tag}_PWR_SS", **T)
        res_between(d, en, lsg, "1k", ref=f"R_DEV_{tag}_PWR_S", **T)
        res_between(d, lsg, "GND", "100k", ref=f"R_DEV_{tag}_PWR_PD", **T)
        if tag == "TWR":
            # tower power only with ALL three seat teeth touching: any open seat
            # line (pulled up to 3V3) turns its N-FET on and holds the gate low
            for k in (1, 2, 3):
                qs = add_ru1j002yntcl(d, ref=f"Q_DEV_TWR_SEAT{k}", **T)
                N(lsg).connect(qs.pin("3")); N("GND").connect(qs.pin("2"))
                N(f"TWR_SEAT_{k}").connect(qs.pin("1"))
    seat_interlock("DEV_FLAT_PWR_SRC", "PWR")              # flat supply off while seated
    # HARDWARE OVERVOLTAGE CUT-OFF: DEV_FEED above ≈ 5.9 V (374k/100k into the
    # MAX9117's 1.252 V reference) turns both power paths off, whatever the
    # firmware does — a mis-set bench supply never reaches the tower's BAT_PROT
    # converters (6 V abs max) or Q_ISO (±12 V).
    from smash.parts.protection import add_max9117exk
    ovp = add_max9117exk(d, ref="U_DEV_OVP", **T)
    N(V3).connect(ovp.pin("VCC")); N("GND").connect(ovp.pin("VEE"))
    N("DEV_OVP_IN").connect(ovp.pin("IN+")); N("DEV_OVP").connect(ovp.pin("OUT"))
    res_between(d, "DEV_FEED", "DEV_OVP_IN", "374k", ref="R_DEV_OVP1", **T)
    res_between(d, "DEV_OVP_IN", "GND", "100k", ref="R_DEV_OVP2", **T)
    cap_to_gnd(d, "DEV_OVP_IN", "1nF", ref="C_DEV_OVP_IN", **T)
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_OVP_VCC", **T)
    # the flat tower has no diode drop: its own cut-off at ≈ 4.37 V (249k/100k)
    ovp2 = add_max9117exk(d, ref="U_DEV_OVP_FLAT", **T)
    N(V3).connect(ovp2.pin("VCC")); N("GND").connect(ovp2.pin("VEE"))
    N("DEV_OVP_FLAT_IN").connect(ovp2.pin("IN+")); N("DEV_OVP_FLAT").connect(ovp2.pin("OUT"))
    res_between(d, "DEV_FEED", "DEV_OVP_FLAT_IN", "249k", ref="R_DEV_OVP_FLAT1", **T)
    res_between(d, "DEV_OVP_FLAT_IN", "GND", "100k", ref="R_DEV_OVP_FLAT2", **T)
    cap_to_gnd(d, "DEV_OVP_FLAT_IN", "1nF", ref="C_DEV_OVP_FLAT_IN", **T)
    cap_to_gnd(d, V3, "100nF", ref="C_DEV_OVP_FLAT_VCC", **T)
    for sig in ("DEV_OVP", "DEV_OVP_FLAT"):                              # red: that cut-off tripped
        led_o = add_ltst_c190krkt(d, ref=f"D_DEV_LED_{sig[4:]}", **T)
        res_between(d, sig, f"D_DEV_LED_{sig[4:]}_A", "1k", ref=f"R_DEV_LED_{sig[4:]}", **T)
        N(f"D_DEV_LED_{sig[4:]}_A").connect(led_o.pin("A")); N("GND").connect(led_o.pin("K"))
    for tag, sig in (("TWR", "DEV_OVP"), ("FLAT", "DEV_OVP_FLAT")):
        qo = add_ru1j002yntcl(d, ref=f"Q_DEV_OVP_{tag}", **T)
        N(f"DEV_{tag}_PWR_LSG").connect(qo.pin("3")); N("GND").connect(qo.pin("2"))
        N(sig).connect(qo.pin("1"))
    # the 5.9 V comparator also drives the flat path (anything above it is above 4.37 V too)

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
            "WBA_NRST": "WBA_NRST", "FIN_SWDIO": "FIN_MCU_SWDIO",
            "FIN_SWCLK": "FIN_MCU_SWCLK", "FIN_NRST": "FIN_MCU_NRST",
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
    # MP25 BOOT0 (the tower pulls BOOT0/BOOT2 HIGH = serial-NAND boot; pulling
    # them LOW = UART/USB serial boot of a blank NAND): probe PB13 (through 1 k,
    # driven low) or the BOOT button (to GND) does it, through a 4th switch per bank (isolated until the
    # tower is powered, so an unpowered MP25 is never back-fed). Channels 2-4 spare.
    res_between(d, "DEV_MCU_MP25_BOOT0", "DEV_TWR_MP25_BOOT0_G", "1k", ref="R_DEV_MP25_BOOT0", **T)
    N("DEV_MCU_MP25_BOOT0").connect(g.pin("PB13"))
    for ref, oe, b_net in (("U_DEV_BUSSW3", "DEV_TWR_OE_N", "TWR_BOOT0"),
                           ("U_DEV_FLATSW3", "DEV_FLAT_OE_N", "BOOT0")):
        bs = DB.add_sn74cb3t3125pwr(d, ref=ref, **T)
        N(V3).connect(bs.pin("VCC")); N("GND").connect(bs.pin("GND"))
        cap_to_gnd(d, V3, "100nF", ref=f"C_{ref[2:]}", **T)
        N("DEV_TWR_MP25_BOOT0_G").connect(bs.pin("1A"))
        N(b_net).connect(bs.pin("1B"))
        N(oe).connect(bs.pin("1~{OE}"))
        for c in (2, 3, 4):                                  # spare: off, both sides grounded
            N(V3).connect(bs.pin(f"{c}~{{OE}}"))
            N("GND").connect(bs.pin(f"{c}A")); N("GND").connect(bs.pin(f"{c}B"))
    res_between(d, "TWR_VDD", "DEV_TWR_VDD_SENSE", "10k", ref="R_DEV_TWR_VDD1", **T)
    res_between(d, "DEV_TWR_VDD_SENSE", "GND", "20k", ref="R_DEV_TWR_VDD2", **T)

    # ── aft fixture: one spring pin per tower aft contact (same contact map) ──
    fx, fy = FIXTURE_CENTRE
    to_twr = {"VDD_SENSE": "TWR_VDD", "EXT_VIN": "TWR_EXT_VIN",
              "EXT_CAN_P": "TWR_CAN_P",
              "EXT_CAN_N": "TWR_CAN_N", "FLEX_GND": "GND"}
    seats = seat_teeth()
    for tooth, ang, net, label, role in aft_contacts():
        if role in ("screw", "key"):
            continue
        pin = DB.add_mill_max_0906(d, ref=f"P_DEV_FIX_{tooth:02d}", **T)
        if tooth in seats:                              # GND contact → seat sense line
            net_ = f"TWR_SEAT_{seats.index(tooth) + 1}"
        else:
            net_ = to_twr.get(net, f"TWR_{label}" if role != "gnd" else "GND")
        N(net_).connect(pin.pin("1"))
        r = FIXTURE_R[tooth % 2]
        a = math.radians(ang)
        locks[pin.ref] = {"position_mm": [round(fx + r * math.cos(a), 4),
                                          round(fy + r * math.sin(a), 4)],
                          "rotation_deg": 0, "face": "top"}

    # (2026-11-22, user) engineer breakouts: every aft-contact signal the
    # probe does not already use, once for a real tower in the fixture
    # (TWR_*) and once for the flat tower on this board (its own nets).
    used = {"CONS_RX", "CONS_TX", "SWO", "NRST", "SWCLK", "SWDIO", "WBA_NRST", "WBA_SWCLK",
            "WBA_SWDIO", "FIN_NRST", "FIN_SWCLK", "FIN_SWDIO", "CAN_P", "CAN_N", "VDD",
            "EXT_VIN1"}          # supply pin: never on a signal header (it sat next to BOOT0)
    brk = sorted(((label, net) for tooth, _a, net, label, role in aft_contacts()
                  if role == "signal" and label not in used and tooth not in seats),
                 key=lambda x: x[0])
    assert len(brk) <= 40, len(brk)
    for hdr, side in (("J_DEV_TWR_IO", "twr"), ("J_DEV_FLAT_IO", "flat")):
        h = add_wurth_61304021121(d, ref=hdr, **T)
        for k in range(1, 41):
            if k <= len(brk):
                label, net = brk[k - 1]
                N(to_twr.get(net, f"TWR_{label}") if side == "twr" else net).connect(h.pin(str(k)))
            else:
                N("GND").connect(h.pin(str(k)))

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
    # the seat spring pins are exposed: ESD array on the three seat lines (they
    # drive unprotected RU1J gates and the probe MCU); 4th channel grounded
    from smash.parts.protection import add_pesd5v0l4uf
    esd_seat = add_pesd5v0l4uf(d, ref="U_DEV_SEAT_ESD", **T)
    N("GND").connect(esd_seat.pin("GND")); N("GND").connect(esd_seat.pin("GND_2"))
    for k in (1, 2, 3):
        N(f"TWR_SEAT_{k}").connect(esd_seat.pin(f"IO{k}"))
    N("GND").connect(esd_seat.pin("IO4"))

    # ── buttons ────────────────────────────────────────────────────────────
    btns = (("S_DEV_MP25_RST", "NRST", "GND"), ("S_DEV_WBA_RST", "WBA_NRST", "GND"),
            ("S_DEV_WAKE", "MAG_WAKE_N", "GND"), ("S_DEV_JUMP", "JUMP_PAD", "GND"),
            ("S_DEV_LAUNCH", "DEV_LAUNCH_SW", "3V3"), ("S_DEV_METER", "DEV_BTN_METER", "GND"),
            ("S_DEV_MCU_BOOT", "DEV_MCU_BOOT0", V3),
            ("S_DEV_MP25_BOOT", "DEV_TWR_MP25_BOOT0_G", "GND"))
    for ref, a_, b_ in btns:
        sw = DB.add_b3u_1000p(d, ref=ref, **T)
        N(a_).connect(sw.pin("K")); N(b_).connect(sw.pin("A"))
    res_between(d, "DEV_LAUNCH_SW", "PIEZO_P", "10k", ref="R_DEV_LAUNCH", **T)   # fakes the piezo
    res_between(d, V3, "DEV_BTN_METER", "10k", ref="R_DEV_BTN_METER", **T)

    # ── LEDs ───────────────────────────────────────────────────────────────
    leds = (("D_DEV_LED_VBUS", "DEV_VBUS", "1.5k", add_ltst_c190gkt),
            ("D_DEV_LED_3V3", V3, "1k", add_ltst_c190gkt),
            ("D_DEV_LED_TWR", "TWR_EXT_VIN", "1k", add_ltst_c190gkt),     # socket powered (never on the cells)
            ("D_DEV_LED_FLAT", "BAT_RAW", "1k", add_ltst_c190gkt),        # flat tower powered
            ("D_DEV_LED_HV", "ACTIVATE_HV", "33k", add_ltst_c190krkt))   # 33 V: 29 mW in the 0402 (10k was 96 mW)
    for ref, net, rv, fn in leds:
        led = fn(d, ref=ref, **T)
        res_between(d, net, f"{ref}_A", rv, ref=f"R_{ref[2:]}", **T)
        N(f"{ref}_A").connect(led.pin("A")); N("GND").connect(led.pin("K"))
    act = add_ltst_c190gkt(d, ref="D_DEV_LED_ACT", **T)
    res_between(d, V3, "D_DEV_LED_ACT_A", "1k", ref="R_DEV_LED_ACT", **T)
    N("D_DEV_LED_ACT_A").connect(act.pin("A")); N("DEV_LED_ACT").connect(act.pin("K"))

    # ── debug castellations (board-local debug nets): a test point at the end
    # of each escape stub, just outside the tile (positions: tile_layout) ──
    from smash.parts.castellations import DEBUG_CASTELLATIONS, RAIL_TEST_POINTS
    for net in [n for nets in DEBUG_CASTELLATIONS.values() for n in nets] + list(RAIL_TEST_POINTS):
        if any(n.name == net for n in d.nets) and not any(c.ref == f"TP_DEV_DBG_{net}" for c in d.chips):
            tp = add_pogo_pad(d, ref=f"TP_DEV_DBG_{net}", manf_pn=None, **T)
            N(net).connect(tp.pin("1"))

    # ── rail monitor: 3 × ADS7138 (8-ch 12-bit, I²C1 with the PAC1941) log every
    # reachable rail + the power handshake lines at each bring-up stage. AVDD =
    # DEV_3V3 is the reference (FSR 3.3 V). Each input: series / divider into
    # 10 nF at the pin (τ ≈ 0.5–1 ms). Rails ≤ 3.3 V: 100 k series (no DC load);
    # above: dividers (main-state rails only, no standby load). ──
    from smash.parts.devboard import add_ads7138irter
    MON = (  # (addr R to GND, [(net, top, bottom or None)] × 8)
        ("11k", [("COMP_3V3", "100k", None), ("COMP_1V8_AON", "100k", None),
                 ("COMP_0V82", "100k", None), ("COMP_0V9", "100k", None),
                 ("COMP_1V8", "100k", None), ("COMP_1V35", "100k", None),
                 ("COMP_2V8", "100k", None), ("COMP_5V", "100k", "100k")]),
        ("33k", [("COMP_5V_RAW", "100k", "100k"), ("REG_IN_MAIN", "100k", "100k"),
                 ("3V3", "100k", None), ("3V3_AON", "100k", None),
                 ("TMR_VDD", "100k", None), ("MAG_1V8", "100k", None),
                 ("ACTIVATE_HV", "1M", "82k"), ("AWR_1V2", "100k", None)]),
        ("100k", [("AWR_1V3", "100k", None), ("AWR_1V8", "100k", None),
                  ("PMIC_PWR_OK", "100k", None), ("PWR_HOLD", "100k", None),
                  ("RADAR_EN", "100k", None),
                  ("BAT_PROT", "100k", "100k"),     # vs the bench / BAT_RAW: Q_ISO drop (body diode = 0.6 V)
                  ("NRST", "100k", None),           # MP25 / PMIC reset: logs every restart (rule #32)
                  ("XV_5V", "100k", "100k")]),      # PA switch + its soft start
    )
    for k, (addr, chans) in enumerate(MON, start=1):
        adc = add_ads7138irter(d, ref=f"U_DEV_MON{k}", **T)
        N(V3).connect(adc.pin("AVDD")); N(V3).connect(adc.pin("DVDD"))
        N("GND").connect(adc.pin("GND")); N("GND").connect(adc.pin("EP"))
        N("DEV_I2C_SCL").connect(adc.pin("SCL")); N("DEV_I2C_SDA").connect(adc.pin("SDA"))
        cap_to_gnd(d, V3, "1uF", ref=f"C_DEV_MON{k}_AVDD", **T)
        cap_to_gnd(d, V3, "1uF", ref=f"C_DEV_MON{k}_DVDD", **T)
        cap_to_gnd(d, f"DEV_MON{k}_DECAP", "1uF", ref=f"C_DEV_MON{k}_DECAP", **T)
        N(f"DEV_MON{k}_DECAP").connect(adc.pin("DECAP"))
        res_between(d, f"DEV_MON{k}_ADDR", "GND", addr, ref=f"R_DEV_MON{k}_ADDR", **T)
        N(f"DEV_MON{k}_ADDR").connect(adc.pin("ADDR"))          # 0x11 / 0x12 / 0x13 (DS Table 2)
        for ch, (net, top, bot) in enumerate(chans):
            pin = adc.pin(f"AIN{ch}")
            if net is None or not any(n.name == net for n in d.nets):
                N("GND").connect(pin)                            # spare input
                continue
            ain = f"DEV_MON{k}_AIN{ch}"
            res_between(d, net, ain, top, ref=f"R_DEV_MON{k}_{ch}", **T)
            if bot:
                res_between(d, ain, "GND", bot, ref=f"R_DEV_MON{k}_{ch}_B", **T)
            cap_to_gnd(d, ain, "10nF", ref=f"C_DEV_MON{k}_{ch}", **T)
            N(ain).connect(pin)
        # ALERT (pin 12) unused: open (DS: open-drain output)

    # ── logic-analyzer header: the inter-tile buses, tapped off the channel ──
    # (outside every tile: the tap is join copper, scrap after depaneling).
    # Odd pins = signal (direct tap), even pins = GND.
    la = ("AWR_SPI_CLK", "AWR_SPI_CS", "AWR_SPI_MOSI", "AWR_SPI_MISO",
          "AWR_RS232_TX", "AWR_RS232_RX", "AWR_SOP2_CTL",
          "WBA_HCI_SCK", "WBA_HCI_NSS", "WBA_HCI_MOSI", "WBA_HCI_MISO", "WBA_HCI_IRQ",
          "WBA_UART_TX", "WBA_UART_RX",
          "SYS_SPI_SCLK", "SYS_SPI_CS_FIN", "SYS_SPI_MOSI", "SYS_SPI_MISO",
          "I2C2_SCL", "I2C2_SDA")
    hla = add_wurth_61304021121(d, ref="J_DEV_LA", **T)
    for k, net in enumerate(la):
        N(net).connect(hla.pin(str(2 * k + 1)))
        N("GND").connect(hla.pin(str(2 * k + 2)))

    # ── antenna test ports (u.FL) on the tower's slot feeds ────────────────
    # They sit on the slot side of the feed matches (the tiles are production
    # boards): into 50 Ω, S1 reads ≈ 3.3 dB low at 2.44 GHz, S4 ≈ 0.7 dB at 4.7 GHz.
    for net in ("ANT_HF_S1", "ANT_HF_S4"):
        uf = DB.add_u_fl_r_smt_1(d, ref=f"J_DEV_{net[4:]}", **T)
        # Hirose land: pad 3 = SIG (the small centre pad), pads 1/2 = the shell's GND tabs
        N(net).connect(uf.pin("3")); N("GND").connect(uf.pin("1")); N("GND").connect(uf.pin("2"))
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
             ("camera_module", "qpd_module"))
# (2026-11-21, user) tiles in STACK ORDER along a straight channel = the LDS
# sleeve unrolled (lanes in sleeve-angle order), alternating above / below it;
# the programming board (socket + debug) is a strip UNDER the tile rows, the
# bus turning down into it past the aft-end tile — the board fits a 221 × 186 mm
# assembly line (2026-11-26, user)
TILE_ORDER = ("aft_end_board", "activation_interface", "wakeup_board", "power_board",
              "companion_compute", "radar_module", "qpd_module", "camera_module")
TILE_KEY_DEG = 191.25          # the sleeve key / lane gap on every tile (potting hole −56.25°)
PROG_H_MM = 74.0               # programming-board strip under the tiles (full board width): USB-C on its left edge, socket at its right end, debug between
CHANNEL_MM = 12.5              # the unrolled sleeve: ~104 lanes at 0.12 mm pitch on the inner layers
# 4 tabs on the strip's slot, none where the bus crosses it (the bus passes a
# fully cut stretch of the slot); x relative to the board centre
PROG_SLOT_TABS_X = (-45.0, -5.0, 40.0, 85.0)
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
_DEBUG_TP_R: dict = {}         # (board, castellation pad) → stub way points [(radius, Δangle°)] past the pad
_FAN_PTS: list = []            # panel (x, y) of every fanned-out test point / shunt part
_FAN_SEGS: list = []           # panel fan-out stub segments


# Per-tile current shunts (bring-up): on the dev panel each consumer tile's copy
# of a main rail is its own net <RAIL>__<TILE>, joined to the channel bus
# through a sense resistor (0.1 Ω, or SHUNT_OVERRIDES) at the end of that tile's castellation stub,
# with a test point either side. Panel only: the tower boards keep the rail.
SHUNT_RAILS = {"BAT_PROT": "power_board", "3V3": "power_board",
               "COMP_5V": "power_board", "COMP_3V3": "power_board"}
SHUNT_PN = ("Panasonic", "ERJ-2BSFR10X")          # 0.1 Ω 1 % 0402, 1/6 W
# Shunts whose tile peak would overload 0.1 Ω: the radar's BAT_PROT carries its
# bucks in DESCENT + chirp, ≈1.1–1.3 A at a 2.5–3.0 V pack (sim/battery/loads.py)
# → 0.1 Ω = 175 mW / 132 mV; 10 mΩ = 17 mW / 13 mV.
SHUNT_OVERRIDES = {("BAT_PROT", "radar_module"):
                   ("10m", "Panasonic", "ERJ-2LWFR010X", "0.01 Ω 1 % 0402")}
_SHUNTS: dict = {}                                 # (tile, rail) → split net name


def _tile_tag(b: str) -> str:
    return {"aft_end_board": "AFT", "activation_interface": "ACT", "wakeup_board": "WAKE",
            "power_board": "PWR", "companion_compute": "COMP", "radar_module": "RADAR",
            "qpd_module": "QPD", "camera_module": "CAM"}[b]


def _add_tile_shunts(d) -> None:
    from smash.parts.mechanical import add_pogo_pad
    from smash.state.net import Net
    from smash.netlist import res_between
    T = dict(board_tag=DIAG)
    for rail, src in SHUNT_RAILS.items():
        old = d.net_by_name(rail)
        if old is None:
            continue
        for b in TILE_ORDER:
            cast = next((c for c in d.chips if c.ref == f"J_CAST_{b}"), None)
            if b == src or cast is None or not any(p.name.split("@")[0] == rail for p in cast.pins):
                continue
            new = f"{rail}__{_tile_tag(b)}"
            refs = {c.ref for c in d.chips if c.board_tag == b} | {cast.ref}
            moved = [k for k in old.pins if k[0] in refs]
            if not moved:
                continue
            old.pins[:] = [k for k in old.pins if k[0] not in refs]
            d.nets.append(Net(name=new, kind=old.kind, voltage_v=old.voltage_v))
            nn = d.net_by_name(new)
            for ref, num in moved:
                nn.pins.append((ref, num))
                for p in d.chip_by_ref(ref).pins:
                    if p.num == num:
                        p.net = new
            tag = new.replace("__", "_")
            val, manf, mpn, desc = SHUNT_OVERRIDES.get(
                (rail, b), ("100m", *SHUNT_PN, "0.1 Ω 1 % 0402"))
            r = res_between(d, new, rail, val, ref=f"R_DEV_SH_{tag}",
                            manf=manf, manf_pn=mpn,
                            description=f"{desc} current-sense (dev panel, per tile)", **T)
            for side, net in (("T", new), ("B", rail)):
                tp = add_pogo_pad(d, ref=f"TP_DEV_SH_{tag}_{side}", manf_pn=None, **T)
                d.connect(net, tp.pin("1"))
            _SHUNTS[(b, rail)] = new


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
    # a dev test point needs its castellation stub on the named board: drop the
    # ones whose net got no pad there (no route out of a tile otherwise)
    from smash.parts.castellations import RAIL_TEST_POINTS
    padded = {(b, n) for b, its in (_LANE_CONTRACT.get("debug") or {}).items() for _a, n in its}
    for c in list(d.chips):
        if not c.ref.startswith("TP_DEV_DBG_"):
            continue
        net = c.ref.removeprefix("TP_DEV_DBG_")
        b = RAIL_TEST_POINTS.get(net)
        cast = next((x for x in d.chips if x.ref == f"J_CAST_{b}"), None) if b else None
        ok = (any(p.name.split("@")[0] == net for p in cast.pins) if cast
              else any(n == net for _b, n in padded))
        if not ok:
            print(f"  WARN: {c.ref}: no castellation pad for {net} — test point dropped")
            remove_component(d, c.ref)
    _add_tile_shunts(d)
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
        else:                                                    # (2026-11-23) stacking-fixture rim notch
            from smash.layout import cavities as CAV             # (every board; joins the rout slot)
            ax, ay = _local_xy(fold.get(name, ((1, 0), (0, 1))), CAV.ALIGN_NOTCH_ANGLE_DEG, 17.0)
            key = (math.degrees(math.atan2(ay, ax)) % 360, CAV.ALIGN_NOTCH_W_MM, CAV.ALIGN_NOTCH_DEPTH_MM)
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
    W = 24.0 + (n - 1) * P / 2 + 23.0
    HT = 2 * (row_y + TILE_BOX_MM / 2 + TILE_EDGE_MM)        # the tile rows
    H = HT + ROUT_MM[1] - ROUT_MM[0] + PROG_H_MM
    YC = H / 2 - HT / 2                                      # channel centre line
    prog_top = -H / 2 + PROG_H_MM                            # strip top edge (slot above it)
    xs = -W / 2 + 24.0
    # the bus turns down into the strip left of the first below-channel tile
    bus_x1 = xs - 2.0
    bus_x0 = bus_x1 - CHANNEL_MM - 0.5                      # lanes turn on the bus pitch (≤ 10.5 mm)
    locks, centres = {}, {}
    for k, name in enumerate(TILE_ORDER):
        above = k % 2 == 0
        cx, cy = xs + k * P / 2, YC + (row_y if above else -row_y)
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
        # debug castellations, rail test points and per-tile shunts: each stub
        # runs radially out past the cut line, then fans out to a free spot
        # (clear of the neighbours' items and stubs, the other tiles, the
        # fiducials and the bus channel); a shunt is TP | resistor | TP in line
        cast = next((c for c in d.chips if c.ref == f"J_CAST_{name}"), None)
        if cast is not None:
            from smash.parts.castellations import RAIL_TEST_POINTS
            items, seen_net = [], set()
            for pin, pad in zip(cast.pins, cast.footprint.pads):
                net = pin.name.split("@")[0]
                if net in seen_net:
                    continue
                if (name, net) in _SHUNTS:
                    tag = _SHUNTS[(name, net)].replace("__", "_")
                    chain = [(f"TP_DEV_SH_{tag}_T", 0.0), (f"R_DEV_SH_{tag}", 2.6), (f"TP_DEV_SH_{tag}_B", 5.2)]
                elif (net not in RAIL_TEST_POINTS          # lane nets: their TP sits on the strip
                      and any(c.ref == f"TP_DEV_DBG_{net}" for c in d.chips)):
                    chain = [(f"TP_DEV_DBG_{net}", 0.0)]
                else:
                    continue
                seen_net.add(net)
                px, py = pad.position_mm
                a = math.degrees(math.atan2(*reversed(rot(px, py))))
                items.append((a, pad, chain))
            fc = TILE_BOX_MM / 2 - 1.5                    # the tile's local fiducials (box corners)
            fids = [(cx + sx * fc, cy + sy * fc) for sx in (-1, 1) for sy in (-1, 1)]
            others = [(xs + j * P / 2, YC + (row_y if j % 2 == 0 else -row_y))
                      for j in range(n) if j != k]
            r0 = LDS_STUB_R_MM + 0.4                      # the fan-out starts here
            pol = lambda rr, ang: (cx + rr * math.cos(math.radians(ang)),
                                   cy + rr * math.sin(math.radians(ang)))

            def seg_d(p, a_, b_):
                (x0, y0), (x1, y1) = a_, b_
                L2 = (x1 - x0) ** 2 + (y1 - y0) ** 2 or 1e-9
                t = max(0.0, min(1.0, ((p[0] - x0) * (x1 - x0) + (p[1] - y0) * (y1 - y0)) / L2))
                return math.hypot(p[0] - x0 - t * (x1 - x0), p[1] - y0 - t * (y1 - y0))

            def seg_seg(a_, b_, c_, d_):
                cr = lambda o, p_, q_: (p_[0] - o[0]) * (q_[1] - o[1]) - (p_[1] - o[1]) * (q_[0] - o[0])
                if (cr(a_, b_, c_) * cr(a_, b_, d_) < 0) and (cr(c_, d_, a_) * cr(c_, d_, b_) < 0):
                    return 0.0                            # proper crossing
                return min(seg_d(a_, c_, d_), seg_d(b_, c_, d_), seg_d(c_, a_, b_), seg_d(d_, a_, b_))
            item_pads = {str(it[1].num) for it in items}
            ends = []                                     # every other stub's end on this tile (+ its join via)
            for pad in cast.footprint.pads:
                if str(pad.num) not in item_pads:
                    qx, qy = rot(*pad.position_mm)
                    rq = math.hypot(qx, qy) or 1.0
                    ends.append((cx + qx / rq * LDS_STUB_R_MM, cy + qy / rq * LDS_STUB_R_MM))
            starts = [(it[0], pol(r0, it[0])) for it in items]     # every item's fan-out start
            # (+ where a shunt would sit in line if it cannot fan out)
            starts += [(it[0], pol(rr, it[0])) for it in items if len(it[2]) > 1
                       for rr in (LDS_STUB_R_MM + 0.1, LDS_STUB_R_MM + 0.6, LDS_STUB_R_MM + 1.1)]
            # nest the arcs: items nearest the channel's flanks go first (inner
            # radius, short swing); those facing the channel straight on go last,
            # over them on a larger radius
            chan = -90.0 if cy > YC else 90.0
            adiff = lambda u, v: abs(((u - v + 180.0) % 360.0) - 180.0)
            for a, pad, chain in sorted(items, key=lambda it: -adiff(it[0], chan)):
                s0 = pol(r0, a)
                best = None
                cands = []
                for Rm in (21.0, 22.6, 24.2, 25.8, 27.4, 29.0, 30.6):
                    for dd in range(0, 151, 3):
                        for sg in ((1, -1) if dd else (1,)):
                            cands.append((Rm, a + sg * dd))
                cands.sort(key=lambda t: (abs(t[1] - a) * t[0] * math.pi / 180 + 0.5 * (t[0] - 21.0)))
                for Rm, b in cands:
                    s1 = pol(Rm, a)
                    nseg = max(1, math.ceil(abs(b - a) / 8.0))     # arc at Rm in ≤ 8° chords
                    arc = [a + (b - a) * j / nseg for j in range(1, nseg + 1)]
                    pts = [pol(Rm + off, b) for _r, off in chain]
                    wp = [s0, s1] + [pol(Rm, t) for t in arc]
                    path = list(zip(wp, wp[1:])) + ([(pts[0], pts[-1])] if len(chain) > 1 else [])
                    obst = [q for a_, q in starts if a_ != a] + ends
                    ok = (all(math.hypot(x - fx_, y - fy_) > 3.0 for x, y in pts for fx_, fy_ in fids)
                          and all(abs(y - YC) > CHANNEL_MM / 2 + 1.5 and abs(y - YC) < HT / 2 - 2.0
                                  and abs(x) < W / 2 - 2.0 for x, y in pts)
                          and all(not (bus_x0 - 1.5 < x < bus_x1 + 1.5 and y < YC) for x, y in pts)
                          and all(seg_d(o, *sg_) > 21.0 for o in others for sg_ in path[1:])
                          and all(abs(q[1] - YC) > CHANNEL_MM / 2 + 0.8 for sg_ in path[1:] for q in sg_)
                          and all(not (bus_x0 - 0.8 < q[0] < bus_x1 + 0.8 and q[1] < YC)
                                  for sg_ in path[1:] for q in sg_)
                          and all(seg_d(q, *sg_) > 1.5 for q in _FAN_PTS for sg_ in path)
                          and all(math.hypot(x - q[0], y - q[1]) > 2.6 for x, y in pts for q in _FAN_PTS)
                          and all(seg_seg(*sg_, *o) > 0.45 for sg_ in path for o in _FAN_SEGS)
                          and all(seg_d(pt, *o) > 1.5 for pt in pts for o in _FAN_SEGS)
                          and all(seg_d(q, *sg_) > 0.6 for q in obst for sg_ in path)
                          and all(math.hypot(x - q[0], y - q[1]) > 1.6 for x, y in pts for q in obst))
                    if ok:
                        best = (Rm, b, pts, path)
                        break
                if best is None and len(chain) > 1:
                    # a shunt facing the channel: the 0402 alone, in line at the
                    # stub end (probe across its pads); its test points go
                    rc = LDS_STUB_R_MM + 0.6
                    x, y = pol(rc, a)
                    locks[chain[1][0]] = {"position_mm": [round(x, 4), round(y, 4)],
                                          "rotation_deg": round(a % 360, 3), "face": "top"}
                    for ref in (chain[0][0], chain[2][0]):
                        remove_component(d, ref)
                    _FAN_PTS.append((x, y))
                    _DEBUG_TP_R[(name, str(pad.num))] = [(rc - 0.48, 0.0)]
                    print(f"  note: {chain[1][0]} in line at the stub end (no room for its test points)")
                    continue
                if best is None:
                    print(f"  WARN: no free spot outside {name} for {chain[0][0]} — dropped")
                    remove_component(d, chain[0][0])
                    continue
                Rm, b, pts, path = best
                nseg = max(1, math.ceil(abs(b - a) / 8.0))
                arc = [(b - a) * j / nseg for j in range(1, nseg + 1)]
                for (ref, _off), (x, y) in zip(chain, pts):
                    locks[ref] = {"position_mm": [round(x, 4), round(y, 4)],
                                  "rotation_deg": round(b % 360, 3) if ref.startswith("R_") else 0,
                                  "face": "top"}
                    _FAN_PTS.append((x, y))
                _FAN_SEGS.extend(path)
                # the stub's way points (radius, panel angle offset from the pad)
                way = [(Rm, 0.0)] + [(Rm, t) for t in arc] + (
                    [(Rm + chain[1][1] - 0.5, b - a)] if len(chain) > 1 else [])
                _DEBUG_TP_R[(name, str(pad.num))] = [(r0, 0.0)] + way
        if m:
            m["holes"] = [(rot(*pos), hd, pl, tg) for pos, hd, pl, tg in m["holes"]]
            m["silk"] = [(ly, [rot(*p) for p in pts], lb) for ly, pts, lb in m.get("silk", [])]
            m["cast_deg"] = sorted((a + phi) % 360 for a in m["cast_deg"])
            if m.get("key"):
                m["key"] = ((m["key"][0] + phi) % 360,) + tuple(m["key"][1:])
    # programming strip under the tiles: USB-C on the left edge, socket at the
    # right end, debug between
    sx, sy = W / 2 - (FIXTURE_KEEPOUT_R_MM + 3.0), -H / 2 + PROG_H_MM / 2
    fixture = (round(sx, 4), round(sy, 4))
    debug = [c for c in d.chips if section.get(c.ref) == DIAG and c.ref not in fixture_refs
             and c.ref not in locks]
    ui = [c for c in debug if c.ref.startswith(("S_DEV_", "D_DEV_"))]
    usb = [c for c in debug if c.ref == "J_DEV_USB"]
    # (2026-11-22) through-hole parts (breakout headers, bench terminal) pierce
    # both faces: own rows, nothing on the bottom under them
    tht = [c for c in debug if c not in ui and c not in usb and any(
        getattr(p, "drill_mm", None) for p in (getattr(c.footprint, "pads", None) or []))]
    rest = [c for c in debug if c not in ui and c not in usb and c not in tht]
    ry1 = prog_top - 7.5                                        # below the strip's corner holes
    ry0 = -H / 2 + 7.5                                          # above the corner holes
    for c in usb:
        w, h, _ox, _oy = _crt_box(c)
        ux = -W / 2 + 2.0 + h / 2
        locks[c.ref] = {"position_mm": [round(ux, 4), round((ry0 + ry1) / 2, 4)],
                        "rotation_deg": 270, "face": "top"}
        usb_w = h + 3.0
    cx0 = -W / 2 + 1.0 + (usb_w if usb else 0.0)
    cx1 = sx - FIXTURE_KEEPOUT_R_MM - 1.5
    # THT band at the strip's bottom (right of the USB-C); the rest fills above it
    rel = _shelf(tht, cx0, 0.0, cx1 - 3.0, gap=1.5)     # 3 mm clear of the strip-corner fiducial
    band = -min((y - _crt_box(next(c for c in tht if c.ref == r))[1] / 2 for r, (_x, y) in rel.items()),
                default=0.0)
    tht_pos = {r: (x, y + ry0 + band) for r, (x, y) in rel.items()}
    if tht_pos:
        ry0 = ry0 + band + 1.5
    top_pos = _shelf(ui, cx0, ry1, cx1)
    used_y = min((y for _x, y in top_pos.values()), default=ry1) - 4.0
    top_pos.update(tht_pos)
    rest_sorted = sorted(rest, key=lambda c: -(_crt_box(c)[0] * _crt_box(c)[1]))
    a_top = (cx1 - cx0) * (used_y - ry0)
    acc, top_set = 0.0, []
    for c in rest_sorted:
        w, h, _ox, _oy = _crt_box(c)
        if acc + (w + 0.6) * (h + 0.6) < 0.55 * a_top:
            top_set.append(c); acc += (w + 0.6) * (h + 0.6)
    bot_set = [c for c in rest_sorted if c not in top_set]
    pos_top = _shelf(top_set, cx0, used_y, cx1)
    pos_bot = _shelf(bot_set, cx0, ry1, cx1)        # ends above the THT band (nothing under it)
    for ref, (x, y) in {**top_pos, **pos_top}.items():
        locks[ref] = {"position_mm": [round(x, 4), round(y, 4)], "rotation_deg": 0, "face": "top"}
    for ref, (x, y) in pos_bot.items():
        locks[ref] = {"position_mm": [round(x, 4), round(y, 4)], "rotation_deg": 0, "face": "bottom"}
    miss = [r for r, (x, y) in {**pos_top, **pos_bot}.items()
            if y - _crt_box(next(c for c in rest if c.ref == r))[1] / 2 < ry0 - 0.5]
    return {"locks": locks, "W": round(W, 1), "H": round(H, 1), "fixture": fixture,
            "centres": centres, "miss": miss, "mech": mech,
            "prog_top": round(prog_top, 4), "yc": round(YC, 4),
            "bus_x": (round(bus_x0, 4), round(bus_x1, 4))}


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
        W, H, pt, yc = layout["W"], layout["H"], layout["prog_top"], layout["yc"]
        bx0, bx1 = layout["bus_x"]
        for sx_ in (-1, 1):                                  # programming board's own corners
            g0.holes.append(_H(position_mm=(sx_ * (W / 2 - 3.5), pt - 3.5), diameter_mm=3.2,
                               plated=False, tag="mount"))
        prog = [(-W / 2 + 0.6, -H / 2 + 0.6), (W / 2 - 0.6, -H / 2 + 0.6),
                (W / 2 - 0.6, pt - 0.6), (-W / 2 + 0.6, pt - 0.6)]
        # the unrolled sleeve: along the channel, turning down into the strip
        # past the aft-end tile
        ch = [(bx0, pt + ROUT_MM[1] - ROUT_MM[0] + 0.5), (bx1, pt + ROUT_MM[1] - ROUT_MM[0] + 0.5),
              (bx1, yc - CHANNEL_MM / 2), (W / 2 - 3.0, yc - CHANNEL_MM / 2),
              (W / 2 - 3.0, yc + CHANNEL_MM / 2), (bx0, yc + CHANNEL_MM / 2)]
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
        "Hold-down: BY HAND while flashing / testing — the 57 spring pins "
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


TAB_MIN_FREE_MM = 3.0         # castellation-free arc a break tab needs (JLC: break ≥ 3 mm)


def _tabs(cast_deg, key, n=3):
    """Tab centre angles: the widest castellation-free gaps, ≥ 90° apart, each
    with ≥ TAB_MIN_FREE_MM of copper-free rim (so breaking the tab cannot tear
    a neighbouring half-hole). Three where three such gaps exist, else two."""
    import math
    from smash.parts.castellations import CAST_PAD_MM
    pts = sorted(set(round(a, 3) for a in cast_deg)) or [0.0]
    gaps = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)] + (360 if i + 1 == len(pts) else 0)
        mid = ((a + b) / 2) % 360
        if key and min(abs(mid - key[0]), 360 - abs(mid - key[0])) < 15:
            continue
        gaps.append((b - a, mid))
    free = lambda w: math.radians(w) * ROUT_MM[0] - CAST_PAD_MM
    out = []
    for w, mid in sorted(gaps, reverse=True):
        if len(out) >= 2 and free(w) < TAB_MIN_FREE_MM:
            break                               # a third tab only in a full-size gap
        if all(min(abs(mid - o[0]), 360 - abs(mid - o[0])) >= 90 for o in out):
            out.append((mid, w))
        if len(out) == n:
            break
    return out


LDS_STUB_R_MM = ROUT_MM[1] + 0.6      # stubs end just outside the cut line
LDS_STUB_W_MM = 0.125                 # the 125 µm track class outside the BGA fields


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
            board = re.sub(r"\d+$", "", m[1].removeprefix("J_CAST_"))
            # debug / rail / shunt pads: on to their fanned-out part (way points)
            way = _DEBUG_TP_R.get((board, pm[1])) or [(LDS_STUB_R_MM, 0.0)]
            pts = [(x, y)]
            for rs, dd in way:                                  # Δ = visual CCW (KiCad y down)
                cd, sd = math.cos(math.radians(dd)), math.sin(math.radians(dd))
                vx, vy = ux * cd + uy * sd, -ux * sd + uy * cd
                pts.append((fx + vx * rs, fy + vy * rs))
            for j, ((sx_, sy_), (ex, ey)) in enumerate(zip(pts, pts[1:])):
                u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/lds/{m[1]}/{pm[1]}" + (f"/{j}" if j else ""))
                segs.append(f'\t(segment\n\t\t(start {sx_:.4f} {sy_:.4f})\n\t\t(end {ex:.4f} {ey:.4f})\n'
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
BUS_STEP_MM, BUS_W_MM = 0.12, 0.125     # 0.48 mm apart on a layer (4 layers), 0.24 on the overflow layers


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
    yc, (bx0, bx1) = lay["yc"], lay["bus_x"]
    y_end = lay["prog_top"] + ROUT_MM[1] - ROUT_MM[0] + 0.5     # the bus ends at the strip's slot
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
        prog = net in prog_nets
        if not prog and x1 - x0 < 1.0:
            continue
        for ang in ln.get("angles", []):
            lanes.append((round(ang % 360, 3), x0, x1, net, prog))
    angles = sorted({a for a, *_ in lanes})
    rank = {a: k for k, a in enumerate(angles)}
    y0 = yc - (len(angles) - 1) * BUS_STEP_MM / 2
    # a lane the programmer uses turns down at x_turn(k): the higher the lane
    # (larger k), the further out it turns, so no two lanes on a layer cross
    x_turn = lambda k: bx1 - k * BUS_STEP_MM                  # same pitch as along the channel
    used, segs, spill = {}, [], 0

    def seg(a, b, layer, net, tag):
        (sx, sy), (ex, ey) = world(*a), world(*b)
        u = uuid.uuid5(uuid.NAMESPACE_URL, f"smash-dev/bus/{net}/{tag}")
        segs.append(f'\t(segment\n\t\t(start {sx:.4f} {sy:.4f})\n\t\t(end {ex:.4f} {ey:.4f})\n'
                    f'\t\t(width {BUS_W_MM})\n\t\t(layer "{layer}")\n\t\t(net "{net}")\n'
                    f'\t\t(uuid "{u}")\n\t)')

    for ang, x0, x1, net, prog in sorted(lanes):
        k = rank[ang]
        if prog:
            x0 = x_turn(k)
        layer = BUS_LAYERS[k % len(BUS_LAYERS)]
        if any(not (x1 + 1.0 < a or x0 - 1.0 > b) for a, b in used.get((k, layer), [])):
            layer = BUS_SPILL[k % 2]; spill += 1
        used.setdefault((k, layer), []).append((x0, x1))
        y = y0 + k * BUS_STEP_MM
        if x1 - x0 > 0.01:
            seg((x0, y), (x1, y), layer, net, ang)
        if prog:
            seg((x0, y), (x0, y_end), layer, net, f"{ang}/down")
    end = txt.rstrip().rfind(")")
    pcb.write_text(txt[:end] + "\n".join(segs) + "\n" + txt[end:])
    return {"tracks": len(segs), "angles": len(angles), "spill": spill,
            "width_mm": round((len(angles) - 1) * BUS_STEP_MM + BUS_W_MM, 2),
            "prog": len({ln[3] for ln in lanes if ln[4]})}


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
    pt = lay["prog_top"]
    local["programmer"] = [(-W / 2 + 4.0, -H / 2 + 12.0), (W / 2 - 4.0, -H / 2 + 12.0),
                           (W / 2 - 10.0, pt - 4.0)]
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
    pt = lay["prog_top"]
    pslot = box(-W / 2 - 1, pt, W / 2 + 1, pt + ROUT_MM[1] - ROUT_MM[0])
    for tx in PROG_SLOT_TABS_X:                              # programming board break tabs
        pslot = pslot.difference(box(tx - TAB_W_MM / 2, pt - 1, tx + TAB_W_MM / 2, pt + 3))
        for k in range(MOUSE_BITES):
            bites.append(world(tx + (k - (MOUSE_BITES - 1) / 2) * 0.8, pt + 1.0))
        ntab += 1
    slots.append(pslot)
    for name, (cx, cy) in lay["centres"].items():
        mm = lay["mech"].get(name, {})
        key = mm.get("key")
        ring = Point(0, 0).buffer(ROUT_MM[1], 180).difference(Point(0, 0).buffer(ROUT_MM[0], 180))
        if key:                                           # the rim notch (stacking fixture) joins the slot
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
        f"- {ntab} break tabs ({TAB_W_MM:g} mm) at the widest castellation-free gaps (three per "
        f"tile where three ≥ {TAB_MIN_FREE_MM:g} mm gaps exist, else two), "
        f"{MOUSE_BITES} × Ø{MOUSE_BITE_D_MM:g} mouse bites each, on the cut line.\\n"
        "- Every tile: the 1.2 × 1.0 mm stacking-fixture notch at 285° (tower frame) is part of its slot.\\n"
        "- PROGRAMMER strip (socket + debug, USB-C on the panel edge): 2 mm slot on its "
        f"tile side, {len(PROG_SLOT_TABS_X)} tabs; with its corner holes it is a stand-alone "
        "tower programmer.\\n"
        "- Traces that cross a slot (castellation escapes, the programmer→channel bus) are "
        "milled through: they only matter on the uncut dev board (dev_board.kicad_pcb).\\n"
        "- ROUTING RULE (both files): a trace may cross a tile's ring ONLY as a straight "
        "radial stub from its own castellation pad (the cut then lands on the pad = the "
        "intended half-hole); never route along or through the ring, and never through a "
        "tab (tabs sit in castellation-free gaps and carry no signals).\\n"
        "- Copper outside the tiles (inter-tile joins, socket, debug) is scrap after depaneling; "
        "nothing inside a tile depends on it. The camera's 0.5 mm Al spreader is bonded after.\\n"
        "- 3 fiducials per side (FID1-3 top, FID4-6 bottom), asymmetric.\\n"
        "- J_DEV_LA (logic analyzer, 2×20): 20 inter-tile bus signals on the odd pins "
        "(direct taps), GND on the even pins. Tap the bus in the channel with the "
        "shortest possible branch, SPI clocks first.\\n"
        "- J_DEV_HF_S1 / J_DEV_HF_S4 (u.FL) sit on the slot side of the feed matches: into 50 Ω, "
        "conducted S1 levels read ≈ 3.3 dB low at 2.44 GHz, S4 ≈ 0.7 dB at 4.7 GHz.\\n"
        "- MP25 BOOT0: S_DEV_MP25_BOOT or probe PB13, through U_DEV_BUSSW3 / "
        "U_DEV_FLATSW3 (enabled with the other debug lines).\\n"
        "- Bring-up test points (BRING_UP.md). Rails and control lines that have a sleeve "
        "lane: TP_DEV_DBG_<net> on the programmer strip, reached over the channel bus. "
        "Board-local debug nets: TP_DEV_DBG_<net> at the end of their castellation stub, "
        "outside the tile. TP_DEV_DBG_ACTIVATE_HV carries 33 V.\\n"
        "- Per-tile current shunts: on the panel, each consumer tile's copy of BAT_PROT, "
        "3V3, COMP_5V and COMP_3V3 is its own net <RAIL>__<TILE>, joined to the channel "
        "bus through R_DEV_SH_<RAIL>_<TILE> (0.1 Ω 0402; 10 mΩ on R_DEV_SH_BAT_PROT_RADAR, which carries up to ≈1.3 A) at the end of that tile's stub; "
        "TP_DEV_SH_..._T (tile side) / _B (bus side) either side where there is room, "
        "otherwise probe across the resistor. The bus via joins at the resistor's outer "
        "pad. Lift a shunt to isolate a tile. The tower boards keep the plain rail name.\\n"
        "- Rail monitor U_DEV_MON1-3 (ADS7138, I²C1 0x11 / 0x12 / 0x13): series 100 k "
        "(dividers above 3.3 V) into 10 nF at each input; the inputs are clamped to "
        "DEV_3V3, so keep the strip powered while the tower is.\\n")
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
    section.update({c.ref: DIAG for c in d.chips if c.ref.startswith(("R_DEV_SH_", "TP_DEV_SH_"))})
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
    # the tower's fine-pitch BGA escapes, on the dev board's tiles too
    from smash.layout.bga_escape import escape_board as _escape_board
    for _ref, _st in _escape_board(d, boards, G.BGA_ESCAPE_REFS).items():
        print(f"  BGA escape {_ref} ({_st['board']}): {_st}")
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
    # The schematic keys each symbol's uuid by its tile SECTION (wakeup_board,
    # ...); the panel writer keyed the footprint (path …) by DEV. Point every
    # footprint at its symbol, or Update PCB from Schematic re-adds them all.
    _txt = pcb.read_text()
    for ref in refs:
        sec = section.get(ref, DEV)
        if sec != DEV:
            _txt = _txt.replace(f'(path "{KS.symbol_path(DEV, ref)}")',
                                f'(path "{KS.symbol_path(sec, ref)}")')
    pcb.write_text(_txt)
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
    # assembly (CPL + BOM from the board's own footprints) + one zip per fab set
    try:
        import zipfile
        from smash.export.assembly import write_assembly
        asm = write_assembly(pcb, OUT / "fab", G.find_kicad_cli())
        print(f"  assembly: {asm['cpl'].relative_to(REPO)} + {asm['bom'].relative_to(REPO)} "
              f"({asm['lines']} lines, {asm['parts']} placed parts"
              + (f"; NOT in the pos file: {', '.join(asm['missing'][:8])}" if asm["missing"] else "") + ")")
        for mode, fdir in pv.get("fab", {}).items():
            zp = OUT / "fab" / f"{DEV}_gerbers_{mode}.zip"
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(fdir.iterdir()):
                    z.write(f, f.name)
    except G.KiCadCliNotFound:
        print("  assembly: SKIPPED (kicad-cli unavailable)")
    import os
    if os.environ.get("SMASH_SKIP_CHECKS") != "1":                 # warnings only
        from smash.export.checks import report as _check_report
        _check_report(pcbs=[pcb], schematics=[OUT / f"{DEV}.kicad_sch"], root=REPO)
        try:
            from smash.validators.electrical import report as _erc_report
            _erc_report(d, "dev board")
        except Exception as _e:
            print(f"Electrical rules check: SKIPPED ({type(_e).__name__}: {_e})")
    print(f"  LDS bus: {bus['tracks']} tracks on {bus['angles']} lane angles, {bus['width_mm']} mm "
          f"wide ({'/'.join(BUS_LAYERS)}; {bus['spill']} on {'/'.join(BUS_SPILL)}); "
          f"{bus['prog']} nets run on to the programmer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
