#!/usr/bin/env python3
"""Smash design generator — builds the full Smash design using nothing
but the `smash` library and emits the KiCad panels + per-config variants.

Originally a twin of the legacy SKiDL `system.py` (now frozen under
`archive/`; see archive/README.md). The `smash` library is the sole
authority — parity with `system.py` is no longer maintained, so the old
byte-diff verification loop is retired. Run:

    python3 generate_maximalist_system.py                # full twin + configs

Boards are built bottom-up — smallest first. Cross-board nets are
get-or-create via `_net()`; whichever board's builder runs first
creates the net, subsequent boards connect onto it.

Status (boards implemented):
    [x] qpd_module               (1 part)
    [x] nfc_antenna_flex         (1 part)
    [ ] nose_connector           (5 parts)
    [ ] camera_module            (9 parts)
    [ ] activation_interface    (22 parts)
    [ ] radar_module            (33 parts)
    [ ] companion_compute       (44 parts + 2 SPI-NAND, ex-companion_io storage)
    [x] wakeup_board            (88 parts)
    [x] power_board             (91 parts)
    [x] flight_board           (108 parts)
"""
from __future__ import annotations

import functools
import os
import json
import pathlib
import re
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "application" / "src"))

from smash.state import (                                              # noqa: E402
    Design, NetHandle, Footprint, Pad, Pin, Flex,
)
from smash.parts.mechanical import (                                   # noqa: E402
    add_mt03_092_qpd, add_nfc_antenna_flex_27x50,
    add_pogo_pad, add_cell_contacts_3, add_cell_solder_tab, add_piezo_disc_smd10t04r111,
    add_mechanical_spacer_34mm,
)
from smash.parts.connectors import (place_lga_lands,                    # noqa: E402
                                    place_branch_flex_launches)
from smash.parts.batteries import add_tlm_1520hpms, add_tlm_1530m       # noqa: E402
from smash.parts.cameras import add_ar0234cssm00suka0_cp               # noqa: E402
from smash.parts.radar import (                                        # noqa: E402
    add_awr2944abgaltrq1, add_awr2e44pbgamxrq1, add_awr1843aop,
)
from smash.parts.regulators import (                                    # noqa: E402
    add_lmr10510xmfe_nopb, add_mcp1640ct_i_chy, add_tps61175pwpr,
)
from smash.parts.motor_drivers import add_drv8428epwpr                  # noqa: E402
from smash.parts.diodes import (add_mbrs340t3g, add_mbrs540t3g,  # noqa: E402
                                add_pmeg040v050epe_qz, add_bat64_06_tp)
from smash.parts.ldos import (                                          # noqa: E402
    add_ldl112pv18r, add_ldl112pv33r, add_stlq020c33r,
    add_lp5907mfx_1_2_nopb, add_lp5907mfx_2_8_nopb, add_tps7a0233pdbvr,
)
from smash.parts.pmics import add_stpmic25apqr                          # noqa: E402
from smash.parts.sensors import add_h3lis331dltr, add_tmp117maidrvr     # noqa: E402
from smash.parts.transceivers import add_tcan1042gvdq1                  # noqa: E402
from smash.parts.mcus import (                                          # noqa: E402
    add_stm32mp255dal3, add_stm32g0b1rei6n,
    add_stm32wba55hgf6tr, add_stm32h562aii6,
)
from smash.parts.flash import (                                         # noqa: E402
    add_ktdm4g4b626bgieat,
    add_mt29f4g01abafdwb_it_f, add_s25hl512tfamhi010, add_sst26wf080b,
    add_sst26vf080a,
)
from smash.parts.mosfets import (                                        # noqa: E402
    add_irlml6402trpbf, add_bss138lt1g, add_dmn6075sq_7, add_dmp6110svt_7,
)
from smash.parts.logic import add_cd74hc4514pw                           # noqa: E402
from smash.parts.oscillators import (                                    # noqa: E402
    add_sit1630ae_s6_dcc_32_768e, add_dsc1001ci5_008_0000,
    add_dsc1001ci5_032_0000, add_dsc1001ci5_040_0000,
)
from smash.parts.passives import (                                       # noqa: E402
    add_capacitor_c0g_0603_avx_sqcs, add_capacitor_x7r_0402_kemet,
    add_we_744043100,
)
from smash.parts.sensors import add_iis2mdctr, add_ism330dhcxtr           # noqa: E402
from smash.parts.opamps import add_ad8603aujz_r2_single_supply             # noqa: E402
from smash.parts.comparators import add_tlv3691idpfr                      # noqa: E402
from smash.parts.optical import add_vbpw34fas, add_vsmb1940x01           # noqa: E402
from smash.parts.hall_sensors import add_drv5032fcqdbzr, add_rr123_1h02_612  # noqa: E402
from smash.parts.usb import add_uj20_c_h_g_msmt_1a_p16_tr_67            # noqa: E402
from smash.netlist import cap_to_gnd, res_between, ind_between          # noqa: E402
from smash.export.canonical_netlist import write_canonical_netlist     # noqa: E402
from smash.export import (                                              # noqa: E402
    write_kicad_pcb, write_kicad_panel, write_all_spacer_steps,
    write_kicad_step, find_kicad_cli, KiCadCliNotFound,
    write_blank_drawing_sheet, write_stackup_step,
    write_stackup_components_step,
    write_consolidated_stackup_stl, write_housing_stl,
    write_gerbers,
)
from smash.layout.boards.smash_evb_v1 import (                          # noqa: E402
    build_panel, build_config_panel,
)
from smash.layout.placer import place_design, size_backbone_spacers     # noqa: E402


# ── get-or-create net helper ─────────────────────────────────────────────

# Auto-classification of well-known power-rail names. Anything matching
# this map is created as `kind="power"` with the listed nominal voltage,
# so the `_v_pin_type_vs_net_kind` validator passes without every call
# site needing to spell out `kind="power", voltage_v=...`. Anything
# NOT in this map stays `kind="signal"` and a mistakenly-connected
# power pin will be caught by the validator.
_AUTO_POWER_RAILS: dict[str, float] = {
    "3V3":          3.3,
    "FLEX_3V3":     3.3,
    "COMP_5V":      5.0,
    "COMP_5V_RAW":  5.0,    # boost output, fin/VM side of the LC filter (rule-sweep F6 — was kind="signal")
    "COMP_3V3":     3.3,    # PMIC BUCK2 — MP25 IO ring (rule-sweep F6 — was kind="signal")
    "COMP_1V8":     1.8,
    "COMP_VPP":     2.5,
    "COMP_1V2":     1.2,
    "COMP_0V9":     0.9,
    "COMP_0V82":    0.82,   # MP25 VDDCORE domain (PMIC BUCK5; DS ROC 0.79–0.842 V)
    "3V3_AON":      3.3,    # nanopower standby domain (TPS7A02 off BAT_RAW; WBA+H3LIS+ST25DV+TLV3691)
    "COMP_2V8":     2.8,
    "AWR_1V0":      1.0,    # AWR2944/2E44P core (legacy builders)
    "AWR_1V2":      1.2,    # AWR1843 core (VDDIN/VIN_SRAM/VNWA, SWRS236)
    "AWR_1V3":      1.3,    # AWR1843 RF front-end (VIN_13RF)
    "AWR_1V8":      1.8,
    "BAT_RAW":      4.0,
    "BAT_PROT":     4.0,
    "ACTIVATE_HV":      33.0,   # aft activation rail (TPS61175 boost off COMP_5V); cap-free, boost sources the wire directly
    "USB_VBUS":     5.0,    # depot USB-C input; crosses nose→power_board (Q_USB_OR ideal diode) at up to the 3 A a non-PD USB-C source can deliver — size the flex as a power rail, not signal
    "REG_IN_MAIN":  4.0,
    "BOOST_OUT":    3.87,
    "VCAP1":        1.2,    # legacy / unused (orphaned — H562 retired)
    "VCAP2":        1.2,
    "WBA_VDD11":    1.1,    # WBA55 SMPS output → core supply
    "CAM_PHY_REG":  1.2,    # AR0234CS internal LDO output (MIPI PHY)
}

# Ground nets — anything matching here gets kind="ground". Aliases are
# handled via merge_nets, so e.g. "GND" merges into FLEX_GND but the
# initial creation still needs the right kind.
_AUTO_GROUND_NETS: set[str] = {"GND", "FLEX_GND"}


def _net(d: Design, name: str, *, kind: str | None = None,
         voltage_v: float | None = None) -> NetHandle:
    """Return a NetHandle for `name`, creating the net if it doesn't
    exist yet. Idempotent — multiple boards can call this with the
    same net name and chain `.connect()` onto the result.

    Also handles the alias case: if `name` doesn't exist as a primary
    net name but does exist as an alias on a merged net (after
    `Design.merge_nets`), return a handle to that merged net rather
    than creating a fresh net with a colliding name.

    `kind` defaults to `None`, which triggers auto-classification:
      - known power-rail names → `kind="power"`, voltage from map
      - known ground-net names → `kind="ground"`
      - everything else        → `kind="signal"`
    Pass an explicit `kind` to override."""
    existing = d.net_by_name(name)
    if existing is None:
        for n in d.nets:
            if name in n.aliases:
                return NetHandle(d, n)
        if kind is None:
            if name in _AUTO_GROUND_NETS:
                kind = "ground"
            elif name in _AUTO_POWER_RAILS:
                kind = "power"
                if voltage_v is None:
                    voltage_v = _AUTO_POWER_RAILS[name]
            else:
                kind = "signal"
        if kind == "ground":
            return d.add_ground_net(name)
        if kind == "power":
            assert voltage_v is not None, \
                f"_net({name!r}, kind='power') requires voltage_v"
            return d.add_power_net(name, voltage_v=voltage_v)
        return d.add_signal_net(name)
    return NetHandle(d, existing)


def _add_antenna_pad(d: Design, *, ref: str, value: str, description: str,
                     board_tag: str):
    """Single-pin TestPoint pad standing in for a flex-etched antenna.
    SKiDL uses `Part("Device", "Antenna")` with a `TestPoint:` footprint;
    smash has no antenna factory yet so we synthesise the Chip inline.
    """
    fp = Footprint(
        name="TestPoint:TestPoint_Pad_1.0x1.0mm",
        package_class="TestPoint pad",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(1.0, 1.0), shape="rect", layer="F.Cu")],
        size_mm=(1.0, 1.0),
        source="kicad",
    )
    fp.ensure_courtyard_clearance()       # ring the lone pad so it can't abut
    return d.add_chip(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name=value, value=value, description=description,
        pins=[Pin(num="1", name="1", type="passive")],
    )


# PCB-surface dielectric foreshortening for a quarter-wave monopole
# printed on F.Cu of an FR4 board. ≈ 0.72 × free-space λ/4 (effective
# εr ~2 for surface micro-strip-like traces with mostly-air above).
_PCB_FORESHORTEN = 0.72

# Speed of light, mm per ns. Used to size printed antennas: free-space
# λ/4 (mm) = (c · ns/mm) / (4 · f_GHz).
_C_MM_PER_NS = 299.79


def _add_printed_pcb_monopole(d: Design, *, ref: str, board_tag: str,
                              freq_ghz: float, description: str | None = None,
                              note: str | None = None) -> Chip:
    """Printed quarter-wave monopole etched directly on the host board's
    F.Cu — no flex extension, no discrete radiating component.

    Trace geometry: L-shape from the feed pad, leg length sized to
    ¼ λ in air × `_PCB_FORESHORTEN` (FR4-surface dielectric loading),
    split half-and-half across two perpendicular legs so the radiator
    fits within ~`leg × leg` mm.

    Mirrors the NFC spiral pattern in `add_nfc_antenna_flex_27x50` —
    the radiator rides as `Footprint.copper_lines` on F.Cu.

    `weight_g = 0`, `height_mm = 0` so the bend / lateral-impact sim
    correctly treats it as a zero-body feature (it flexes WITH the
    PCB; there's no chip-body corner whose lever arm pulls on a
    solder joint). The footprint envelope is set to the radiator's
    real bounding box + IPC-7351 courtyard so the placer keeps other
    chips off the antenna area.

    Used for the bring-up / programming radios (WiFi 2.4 GHz, RF44
    4.4 GHz) where some loss / mismatch is acceptable. The LoRa-868
    radios still need real flex monopoles — λ/4 at 868 MHz is
    ~62 mm even with foreshortening, too long for the Ø34 nose tile.
    """
    leg_mm = (_C_MM_PER_NS / (4.0 * freq_ghz) * _PCB_FORESHORTEN) / 2.0

    # The body envelope is centred at the footprint origin (same
    # convention as `add_nfc_antenna_flex_27x50`) — the placer's
    # bbox calc reaches |W/2| from the placement centre. Feed pad
    # sits just inside one corner; the L-shape trace runs along
    # two perpendicular edges.
    W = H = round(leg_mm + 0.2, 2)              # +0.2 mm body margin around trace
    inset = 0.5                                 # pad/trace inset from edge
    feed_xy = (-W / 2 + inset, -H / 2 + inset)
    feed_pad = Pad(num="1", position_mm=feed_xy,
                   size_mm=(1.0, 1.0), shape="rect", layer="F.Cu")
    monopole_pts = [
        feed_xy,
        (W / 2 - inset, -H / 2 + inset),
        (W / 2 - inset, +H / 2 - inset),
    ]
    crt = 0.25                                  # IPC-7351 courtyard clearance
    # Footprint name embeds frequency for clarity ("PCB_Monopole_2G4",
    # "PCB_Monopole_4G4") — matches the naming style of the SamacSys
    # footprints already in the catalogue.
    tag = f"{freq_ghz:.1f}".replace(".", "G")
    fp = Footprint(
        name=f"PCB_Monopole_{tag}",
        package_class="Printed PCB monopole (F.Cu trace)",
        pads=[feed_pad],
        copper_lines=[{"layer": "F.Cu", "width_mm": 0.5,
                       "points": monopole_pts}],
        body_outline=[(-W/2, -H/2), (+W/2, -H/2), (+W/2, +H/2), (-W/2, +H/2)],
        courtyard=[(-W/2 - crt, -H/2 - crt), (+W/2 + crt, -H/2 - crt),
                   (+W/2 + crt, +H/2 + crt), (-W/2 - crt, +H/2 + crt)],
        size_mm=(W, H),
        height_mm=0.0,
        source="project",
    )
    return d.add_chip(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name=f"PCB_MONOPOLE_{tag}", value=f"PCB_MONOPOLE_{tag}",
        description=description or (
            f"{freq_ghz:.1f} GHz quarter-wave monopole — printed on "
            f"F.Cu of the host board, ~{2 * leg_mm:.0f} mm L-shape "
            "trace. Lossy / poorly-matched on purpose; acceptable for "
            "bring-up / programming radios where a real flex antenna "
            "isn't worth the assembly cost."),
        pins=[Pin(num="1", name="1", type="passive")],
        weight_g=0.0, height_mm=0.0,
        note=note,
    )


def _add_testpoint(d: Design, *, ref: str, board_tag: str):
    """1.5 mm-Ø round TestPoint pad. SKiDL uses Part("Connector", "TestPoint",
    footprint=FP_TP) with FP_TP="TestPoint:TestPoint_Pad_D1.5mm"."""
    fp = Footprint(
        name="TestPoint:TestPoint_Pad_D1.5mm",
        package_class="TestPoint pad (1.5 mm Ø)",
        pads=[Pad(num="1", position_mm=(0.0, 0.0),
                  size_mm=(1.5, 1.5), shape="circle", layer="F.Cu")],
        size_mm=(1.5, 1.5),
        source="kicad",
    )
    fp.ensure_courtyard_clearance()       # ring the lone pad so it can't abut
    return d.add_chip(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name="TestPoint", value="TestPoint",
        description="1.5 mm Ø round TestPoint pad",
        pins=[Pin(num="1", name="1", type="passive")],
    )


# ── boards ────────────────────────────────────────────────────────────────

def build_qpd_module(d: Design) -> None:
    """Marktech MT03-092 quadrant photodiode behind a 1064 nm bandpass
    lens. Photovoltaic mode: each anode → TIA on the same flex tile,
    common cathode → QPD_VREF (1.65 V) — the SAME potential the TIAs
    servo the anodes to, so every quadrant sits at TRUE zero bias.
    (Tying the cathode to GND with the anodes held at the 1.65 V
    virtual ground forward-biased all four junctions and railed the
    TIAs — the bug fixed in the datasheet audit.) Datasheet pin map
    (DS p2, verified): pin 2 = common cathode (backside butt weld),
    pin 5 = NC, anodes Q1→4, Q2→6, Q3→3, Q4→1 — so QPD_A..D = Q1..Q4
    (clockwise from top-left looking into the window).

    Net names are the *natural* per-board names from system.py. When
    flight_board's TIA wiring later connects to the same pins under
    different names (e.g. `QPD_TIA_A_INM`), smash auto-merges and
    keeps both names as aliases on the resulting net."""
    qpd = add_mt03_092_qpd(d, ref="U_QPD", board_tag="qpd_module")

    _net(d, "QPD_A").connect(qpd.pin("4"))
    _net(d, "QPD_VREF").connect(qpd.pin("2"))   # cathode common = the anodes' virtual-ground potential
    _net(d, "QPD_C").connect(qpd.pin("3"))
    _net(d, "QPD_B").connect(qpd.pin("6"))
    _net(d, "QPD_D").connect(qpd.pin("1"))


def build_companion_compute(d: Design) -> None:
    """STM32MP255 — the SINGLE system brain (consolidation): the Cortex-M33
    runs ArduPilot as the autonomous flight controller (M33-TD boot) + is the
    firmware root; the A35 + NPU run perception/planning; FC↔companion comms are
    on-chip (RPMsg). It owns the flight sensors, radar SPI, fins bus, CAN
    gateway, launch-detect ADC, WBA55 link, and power supervision — all wired in
    the M33 flight block below. Plus SMARTsemi KTDM4G4B626BGIEAT DDR4
    (4 Gbit, 512 MB) + 2× SPI-NAND storage + decoupling. The DQ bus uses the
    ST AN5724 DDR4 reference swizzle verbatim (within-byte, hardware-transparent
    — matches the ST footprint 1:1); the A/C bus keeps the ST reference mapping
    where it carries over. DDR4-specific A/C signals (ACT_n, BG0, muxed A14-16,
    PAR, ALERT_n) are DERIVED — cross-check vs the DDR4 reference."""
    BTAG = "companion_compute"

    # ── STM32MP255 — VFBGA-361 (10×10 mm), the AL/DAL3 variant ──────
    # Wired against the DAL3 SamacSys ballout (per-package authority).
    # vs the FAK3 (VFBGA-424): pin names use single underscores
    # (DDR_Ax / CSI_x), DQS drops the underscore-N (DDR_DQS0N), and the
    # power-rail balls differ in count — so power/ground are wired by
    # whatever balls the package exposes rather than fixed loops.
    mpu = add_stm32mp255dal3(d, ref="U_MPU", board_tag=BTAG)

    # Supply rails — the FULL power tree (closes the long-deferred
    # "STPMIC2 power-tree pass": VDDCORE + 49 other power/strap balls
    # were floating, and DS14284 §3.9.1 requires VDD + VDDA18AON +
    # VDDCPU + VDDCORE just to START).
    for p in mpu.pins:
        if re.fullmatch(r"VDD_\d+", p.name):
            _net(d, "COMP_3V3").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VDDCPU_\d+", p.name):
            _net(d, "COMP_0V9").connect(mpu.pin(p.num))   # 0.87–0.935 V hi-perf point ✓
        elif (re.fullmatch(r"VDDCORE_\d+", p.name)
              or p.name in ("VDDCSI", "VDDDSI", "VDDLVDS", "VDDCOMBOPHY",
                            "VDDCOMBOPHYTX", "VDDPCIECLK")):
            # 0.82 V core (ROC 0.79–0.842 V — the 0.9 V CPU rail is OUT of
            # range → dedicated PMIC BUCK5 rail). The six PHY domains ride
            # it per DS: "VDDCSI, VDDDSI, VDDLVDS, VDDCOMBOPHY,
            # VDDCOMBOPHYTX and VDDPCIECLK are usually connected to
            # VDDCORE" — this also powers the camera config's CSI PHY.
            _net(d, "COMP_0V82").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VDDGPU_\d+", p.name):
            # GPU/NPU domain (perception runs on the NPU): 0.8 V typ →
            # shares the 0.82 V core rail (low DVFS point). Give it its
            # own buck later if NPU throughput needs the 0.9 V point.
            _net(d, "COMP_0V82").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VDDQDDR_\d+", p.name):
            _net(d, "COMP_1V2").connect(mpu.pin(p.num))   # DDR4 I/O = 1.2 V
        elif p.name in ("VDDA18AON", "VDDA18PLL1", "VDDA18PLL2", "VDDA18PLL3",
                        "VDDA18DDR", "VDDA18ADC", "VDDA18CSI", "VDDA18DSI",
                        "VDDA18LVDS", "VDDA18COMBOPHY"):
            _net(d, "COMP_1V8").connect(mpu.pin(p.num))   # 1.8 V analog domains
        elif re.fullmatch(r"VDDIO[1234](_\d+)?", p.name):
            # VDDIO2 = the NAND OSPI bank (PE8..15 — 3.3 V parts);
            # VDDIO4 = the PB bank (SYS_SPI / WBA HCI / I2C2, all 3.3 V).
            # ⚠ VDDIO1 (PE2/3/4) + VDDIO3 (PD0..11) carry the AWR SPI,
            # whose VIOIN runs 1.8 V — at 3.3 V this bank mismatches the
            # radar interface (open decision: re-pin the radar SPI into a
            # dedicated 1.8 V bank, or flip the AWR VIOIN+QSPI flash to
            # 3.3 V per the TI EVM). 3.3 V chosen meanwhile because the
            # PD bank's OTHER tenants (PWR_HOLD, COMP_OUT, SYS_SPI_CS,
            # IMU3_INT) are all 3.3 V signals.
            _net(d, "COMP_3V3").connect(mpu.pin(p.num))
        elif re.fullmatch(r"VSS_\d+", p.name) or p.name in ("VSSA", "VSSAON"):
            _net(d, "GND").connect(mpu.pin(p.num))
    _net(d, "COMP_3V3").connect(mpu.pin("VBAT"))
    _net(d, "COMP_3V3").connect(mpu.pin("VDD33UCPD"))   # UCPD unused — powered-safe
    # ADC reference (QPD + sensor channels): buffer-off input mode —
    # VREF+ = VDDA18ADC level, VREF− to analog ground.
    _net(d, "COMP_1V8").connect(mpu.pin("VREF+"))
    _net(d, "GND")     .connect(mpu.pin("VREF-"))
    # USB2 PHY impedance calibration (depot USB rides USB3DR): RTXRTUNE =
    # 200 Ω ±1 % to GND per DS. The unused USBH PHY (DP/DM open) keeps
    # its TXRTUNE open.
    res_between(d, "USB_TXRTUNE", "GND", "200",
                ref="R_MPU_TXRTUNE", board_tag=BTAG)
    _net(d, "USB_TXRTUNE").connect(mpu.pin("USB3DR_TXRTUNE"))
    _net(d, "V08_CAP") .connect(mpu.pin("V08CAP"))
    cap_to_gnd(d, "V08_CAP", "2.2uF", ref="C_MPU_V08CAP", board_tag=BTAG)
    # Local decoupling for the newly-wired domains (bulk lives at the
    # PMIC; HF bypass pairs ride the ECM laminate). Local bulk is a
    # single 0603 2.2 µF (a 22 µF tantalum cost too much joint area at
    # the saturated power↔companion gap, 53 crossing nets in core_radar).
    cap_to_gnd(d, "COMP_0V82", "2.2uF", ref="C_MPU_0V82_BULK", board_tag=BTAG)
    cap_to_gnd(d, "COMP_0V82", "100nF", ref="C_MPU_0V82_1",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_0V82", "100nF", ref="C_MPU_0V82_2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V8",  "100nF", ref="C_MPU_18A_1",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V8",  "100nF", ref="C_MPU_18A_2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2",  "100nF", ref="C_MPU_QDDR_1",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2",  "100nF", ref="C_MPU_QDDR_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── System clocks — shock-tolerant MEMS oscillators in bypass mode ──
    # The MP25 needs an external HSE + LSE; both are MEMS clipped-sine
    # parts (no quartz — survives the axial acceleration shock) driving the IN pin
    # with the OUT pin left NC (HSEBYP/LSEBYP=1, no crystal feedback path),
    # mirroring the WBA55 HSE on the wakeup tile.
    #
    # HSE — 40 MHz into OSC_IN (R1); OSC_OUT (R2) NC.
    # feature="clock": rides the bottom face beneath the MP25's OSC balls
    # (the top face is full with the BGA + DDR4 + NAND).
    hse_osc = add_dsc1001ci5_040_0000(d, ref="Y_MPU_HSE", board_tag=BTAG,
                                      feature="clock")
    _net(d, "COMP_3V3")   .connect(hse_osc.pin("1"))  # STANDBY# tied high
    _net(d, "GND")        .connect(hse_osc.pin("2"))
    _net(d, "COMP_HSE_IN").connect(hse_osc.pin("3"))  # OUT
    _net(d, "COMP_3V3")   .connect(hse_osc.pin("4"))  # VDD
    _net(d, "COMP_HSE_IN").connect(mpu.pin("OSC_IN"))   # R1
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_MPU_HSE_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG)
    #
    # LSE — 32.768 kHz into OSC32_IN (M2); OSC32_OUT (M1) NC. Real LSE
    # (not internal LSI) so the Linux/flight RTC keeps accurate wall-clock
    # time for logs + cert validity. SiT1630 pins: 1=GND, 2/3=NC(→GND),
    # 4=VDD, 5=OUT.
    lse_osc = add_sit1630ae_s6_dcc_32_768e(d, ref="Y_MPU_LSE", board_tag=BTAG,
                                           feature="clock")
    _net(d, "GND")        .connect(lse_osc.pin("1"))
    _net(d, "GND")        .connect(lse_osc.pin("2"))  # NC — datasheet: GND or float
    _net(d, "GND")        .connect(lse_osc.pin("3"))  # NC — datasheet: GND or float
    _net(d, "COMP_3V3")   .connect(lse_osc.pin("4"))  # VDD
    _net(d, "COMP_LSE_IN").connect(lse_osc.pin("5"))  # OUT
    _net(d, "COMP_LSE_IN").connect(mpu.pin("OSC32_IN"))  # M2
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_MPU_LSE_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # FC↔companion links (UART4 console + SWD to the H562) REMOVED — the M33
    # IS the flight controller now, so M33↔A35 comms are on-chip (RPMsg / shared
    # SRAM). PD11/PD10/PA13/PA14/PA15 are freed for the flight wiring below.

    # OCTOSPI → two 512 MB Micron SPI NAND dies (1 GB total) co-located on
    # THIS tile (storage bus entirely on-tile — crosses no board-to-board
    # joint). Shared quad bus (CLK + IO0-3) with a per-die chip-select; the
    # two physical dies give die-level A/B rootfs redundancy. Replaces the
    # parallel x8 NAND that used to sit on companion_io.
    _net(d, "NAND_OSPI_CLK").connect(mpu.pin("PD13"))
    _net(d, "NAND_OSPI_IO0").connect(mpu.pin("PE15"))
    _net(d, "NAND_OSPI_IO1").connect(mpu.pin("PE12"))
    _net(d, "NAND_OSPI_IO2").connect(mpu.pin("PE11"))
    _net(d, "NAND_OSPI_IO3").connect(mpu.pin("PE8"))
    _net(d, "NAND_OSPI_CS0").connect(mpu.pin("PB12"))
    _net(d, "NAND_OSPI_CS1").connect(mpu.pin("PE9"))
    for die, cs in (("A", "NAND_OSPI_CS0"), ("B", "NAND_OSPI_CS1")):
        nand = add_mt29f4g01abafdwb_it_f(d, ref=f"U_NAND_{die}",
                                         board_tag=BTAG)
        _net(d, cs)             .connect(nand.pin("1"))   # CS#
        _net(d, "NAND_OSPI_IO1").connect(nand.pin("2"))   # SO/IO1
        _net(d, "NAND_OSPI_IO2").connect(nand.pin("3"))   # WP#/IO2
        _net(d, "GND")          .connect(nand.pin("4"))   # VSS
        _net(d, "NAND_OSPI_IO0").connect(nand.pin("5"))   # SI/IO0
        _net(d, "NAND_OSPI_CLK").connect(nand.pin("6"))   # SCK
        _net(d, "NAND_OSPI_IO3").connect(nand.pin("7"))   # HOLD#/IO3
        _net(d, "COMP_3V3")     .connect(nand.pin("8"))   # VCC
        cap_to_gnd(d, "COMP_3V3", "100nF", ref=f"C_NAND_{die}_VCC",
                   embedded_cap_absorbs=True, board_tag=BTAG)
        cap_to_gnd(d, "COMP_3V3", "1uF", ref=f"C_NAND_{die}_BULK",
                   board_tag=BTAG)

    # MIPI CSI-2 (DCMIPP, 2-lane)
    _net(d, "CAM_CSI_CLK_P").connect(mpu.pin("CSI_CKP"))
    _net(d, "CAM_CSI_CLK_N").connect(mpu.pin("CSI_CKN"))
    _net(d, "CAM_CSI_D0_P") .connect(mpu.pin("CSI_D0P"))
    _net(d, "CAM_CSI_D0_N") .connect(mpu.pin("CSI_D0N"))
    _net(d, "CAM_CSI_D1_P") .connect(mpu.pin("CSI_D1P"))
    _net(d, "CAM_CSI_D1_N") .connect(mpu.pin("CSI_D1N"))
    _net(d, "CSI_REXT").connect(mpu.pin("CSI_REXT"))
    res_between(d, "CSI_REXT", "GND", "12k", ref="R_MPU_CSI_REXT", board_tag=BTAG)
    _net(d, "CAM_EXTCLK").connect(mpu.pin("PA8"))

    # ═══════════════════════════════════════════════════════════════════════
    # FLIGHT CONTROL — Cortex-M33. Consolidation: the M33 is the autonomous
    # flight controller (M33-TD boot) and firmware root, replacing the former
    # H562; the A35 + NPU run perception/planning; FC↔companion is on-chip
    # RPMsg. Pins are RIF-assignable to the M33 secure domain. The allocation
    # is AF-validated against the DAL3 table (reused from the FAK3 by name).
    # ═══════════════════════════════════════════════════════════════════════

    # System control / sensor / payload bus (SYS_I2C = I2C1)
    _net(d, "SYS_I2C_SCL").connect(mpu.pin("PG13"))   # I2C1_SCL
    _net(d, "SYS_I2C_SDA").connect(mpu.pin("PI1"))    # I2C1_SDA

    # Radar host SPI (SPI1) — control + host-SPI boot stream + detections in
    # from the AWR1843AOP. The radar runs its own detection chain on-chip
    # (C674x DSP + HWA) and returns a point cloud / object list over this link;
    # AWR_DRDY is its data-ready interrupt. See build_radar_module_awr1843aop.
    _net(d, "AWR_SPI_CLK") .connect(mpu.pin("PD11"))  # SPI1_SCK
    _net(d, "AWR_SPI_MISO").connect(mpu.pin("PE2"))   # SPI1_MISO
    _net(d, "AWR_SPI_MOSI").connect(mpu.pin("PE4"))   # SPI1_MOSI
    _net(d, "AWR_SPI_CS")  .connect(mpu.pin("PD2"))   # SPI1_NSS
    _net(d, "AWR_NRESET").connect(mpu.pin("PI6"))
    _net(d, "AWR_FAULT") .connect(mpu.pin("PI7"))
    _net(d, "RADAR_EN")  .connect(mpu.pin("PE10"))
    _net(d, "AWR_DRDY")  .connect(mpu.pin("PF1"))     # radar detections-ready IRQ (EXTI)

    # No gigabit RGMII to the radar: the AWR1843AOP streams *detections*, not
    # raw range-Doppler frames, over the SPI link above. The former MP25 GMAC
    # pins (PA15/PC1/PH10/PH11/PA13/PC0 + PC2/PH12/PH13/PA11/PA14) are freed.
    # (AWR2944/2E44P range-Doppler-over-RGMII path retired with the AoP swap.)

    # (Nose contact switch deleted — impact is sensed by the piezo disk
    # (fin_ble_board top since the 2026-07-31 stack reorder), which reads
    # the deceleration. PD10 has since been taken by H3LIS_INT1.)
    # (Nose status LEDs RETIRED with the IR-link change — PG7/PG8 freed;
    # muzzle state is queried over the IR service link now.)

    # Fins/actuator node bus (SYS_SPI master, SPI2)
    _net(d, "SYS_SPI_SCLK")  .connect(mpu.pin("PB0"))   # SPI2_SCK
    _net(d, "SYS_SPI_MISO")  .connect(mpu.pin("PB6"))   # SPI2_MISO
    _net(d, "SYS_SPI_MOSI")  .connect(mpu.pin("PB2"))   # SPI2_MOSI
    _net(d, "SYS_SPI_CS_FIN").connect(mpu.pin("PD6"))   # GPIO chip-select

    # Flight sensors (mag + 3× IMU) — I²C masters on the M33; the sensors live
    # on the sensor tile and reach here over the LGA backbone.
    _net(d, "I2C2_SCL").connect(mpu.pin("PB5"))   # I2C2: mag + IMU1
    _net(d, "I2C2_SDA").connect(mpu.pin("PB4"))
    _net(d, "I2C3_SCL").connect(mpu.pin("PH6"))   # I2C3: IMU2 + IMU3 (SA0 split)
    _net(d, "I2C3_SDA").connect(mpu.pin("PH2"))
    _net(d, "MAG_DRDY").connect(mpu.pin("PE1"))    # EXTI
    _net(d, "IMU1_INT").connect(mpu.pin("PE5"))
    _net(d, "IMU2_INT").connect(mpu.pin("PE7"))
    _net(d, "IMU3_INT").connect(mpu.pin("PD7"))
    _net(d, "H3LIS_INT1").connect(mpu.pin("PD10"))  # EXTI10 — ±400 g launch
    # witness (moved off the WBA with the IR-wake change; alive from
    # Ready (merged stage), quantitative setback beside the piezo's COMP_OUT edge)

    # Launch detect — QPD TIA outputs (ADC) + piezo comparator + activation
    _net(d, "QPD_TIA_A").connect(mpu.pin("PB11"))  # ADC1
    _net(d, "QPD_TIA_B").connect(mpu.pin("PG15"))  # ADC1
    _net(d, "QPD_TIA_C").connect(mpu.pin("PI11"))  # ADC1
    _net(d, "QPD_TIA_D").connect(mpu.pin("PG11"))  # ADC2
    _net(d, "COMP_OUT").connect(mpu.pin("PD5"))         # TLV3691 piezo comparator EXTI
    _net(d, "ACTIVATE_SET").connect(mpu.pin("PE0"))
    _net(d, "ACTIVATE_CONFIRM").connect(mpu.pin("PD9"))

    # WBA55 wake/BLE radio: HCI (SPI3 host) + LPUART (firmware/console) + boot
    # straps. The M33 is the firmware root that flashes the WBA55.
    _net(d, "WBA_HCI_SCK") .connect(mpu.pin("PE3"))   # SPI3_SCK
    _net(d, "WBA_HCI_MISO").connect(mpu.pin("PB10"))  # SPI3_MISO
    _net(d, "WBA_HCI_MOSI").connect(mpu.pin("PB8"))   # SPI3_MOSI
    _net(d, "WBA_HCI_NSS") .connect(mpu.pin("PE13"))
    _net(d, "WBA_HCI_IRQ") .connect(mpu.pin("PB9"))   # host-wake EXTI
    _net(d, "WBA_UART_TX").connect(mpu.pin("PA10"))   # USART2_RX ← WBA55 TX
    _net(d, "WBA_UART_RX").connect(mpu.pin("PA4"))    # USART2_TX → WBA55 RX
    # WBA reset via Q_WBA_RST gate (HIGH = reset) — rule-sweep F1: PB3
    # is a TT pin on VDDIO4/COMP_3V3; tied straight onto the 3V3_AON-
    # pulled WBA_NRST it back-fed ~280 µA through the clamp into the
    # dead MP25 all standby (28 µA floor → ~310 µA). A FET gate has no
    # clamp path. With BOOT0 (PI10) this is the post-pot WBA reflash +
    # hung-radio recovery mechanism.
    _net(d, "WBA_RST_CMD").connect(mpu.pin("PB3"))    # HIGH = reset WBA
    _net(d, "WBA_BOOT0").connect(mpu.pin("PI10"))     # boot strap

    # Control + status GPIO
    _net(d, "PWR_HOLD")  .connect(mpu.pin("PD0"))
    _net(d, "RF_SW_CTRL").connect(mpu.pin("PD4"))
    _net(d, "GPIO_EXT_0").connect(mpu.pin("PB7"))
    _net(d, "GPIO_EXT_1").connect(mpu.pin("PD3"))
    _net(d, "GPIO_EXT_2").connect(mpu.pin("PB1"))
    _net(d, "GPIO_EXT_3").connect(mpu.pin("PD8"))
    # (nose status LEDs dropped — they crossed the companion↔flight sensor
    # joint, which is the land-budget bottleneck; status goes over CAN/BLE.)

    # Power supervision — orphans now reach the M33 (battery/eFuse/thermal);
    # the STPMIC25 is the MP25's own PMIC (PMIC control wired in the power tree).
    _net(d, "BAT_ISO_DRIVE").connect(mpu.pin("PE6"))  # ideal-diode low-drop enable (out; series R on power_board lets the USB interlock win)
    # PG10 / PF15 freed: eFuse BAT_PGOOD / BAT_IMON removed with the eFuse
    _net(d, "TMP1_ALERT") .connect(mpu.pin("PD1"))    # thermal trip EXTI
    _net(d, "PMIC_PWR_OK").connect(mpu.pin("PI4"))

    # ── EXT_CAN client-extension gateway — FDCAN1 controller side ──────────
    # The MP25 FDCAN1 drives EXT_CAN_TX/RX; the TCAN1042 transceiver itself
    # now lives on flight_board (moved off companion_compute to free top-face
    # room for the un-rotated DDR4 + SPI-NAND). EXT_CAN_TX/RX cross to the
    # transceiver over the flight↔companion LGA backbone. A standard CAN bus
    # is exposed at the activation + nose connectors so third-party CAN
    # payloads can join; the M33 bridges EXT_CAN ↔ SYS_SPI/I2C.
    _net(d, "EXT_CAN_TX").connect(mpu.pin("PD15"))   # FDCAN1_TX
    _net(d, "EXT_CAN_RX").connect(mpu.pin("PD14"))   # FDCAN1_RX

    # ── Depot USB (USB3DR dual-role, Full-speed gadget) ─────────────────
    # The post-potting depot interface: exposed at the NOSE (the only access in
    # that phase), it presents a USB-Ethernet gadget for SSH into A35 Linux +
    # diagnostics, and USB-DFU for signed firmware pushes. FULL-SPEED on purpose
    # — HS (480 Mbps) can't survive the ~4 LGA joints from companion to nose;
    # FS (12 Mbps) is robust over that and ample for SSH + a depot rootfs push.
    # Depot power DOES come in over USB VBUS (USB_VBUS → Q_USB_OR ideal diode on
    # power_board + Q_USB_WAKE/Q_USB_WAKE2 wake; Q_ISO's reverse-block keeps the
    # cells at zero load during the session) — the old "power on the nose BAT_PROT
    # pad" note predated the USB-C wake work.
    _net(d, "USB_DP").connect(mpu.pin("USB3DR_DP"))
    _net(d, "USB_DM").connect(mpu.pin("USB3DR_DM"))
    _net(d, "USB_VBUS_DET").connect(mpu.pin("PC10"))   # USB3DR_VBUSEN (host-attached sense)
    _net(d, "COMP_3V3")    .connect(mpu.pin("VDD33USB"))
    _net(d, "COMP_1V8").connect(mpu.pin("VDDA18USB"))
    cap_to_gnd(d, "COMP_3V3", "1uF", ref="C_USB_33", board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V8", "100nF", ref="C_USB_18",
               embedded_cap_absorbs=True, board_tag=BTAG)
    # PC10 = USB3DR_VBUSEN ("VBUS valid" sense for the device stack),
    # strapped permanently high (rule-sweep F4): the depot session powers
    # the whole round from VBUS, so whenever the MP25 runs with a cable
    # in, VBUS is by construction present — a real divider off USB_VBUS
    # would spend a crossing land for no information. (Ref name is a
    # fossil: this is a pull-UP.)
    res_between(d, "COMP_3V3", "USB_VBUS_DET", "100k",
                ref="R_USB_VBUS_PD", board_tag=BTAG)

    # ── Stage-1 factory debug (JTAG/SWD + reset + BOOT0) ────────────────
    # Reached via the aft activation array (the once-only, pre-pot interface).
    # This is the MP25's own debug port (the H562↔MP25 SWD link is gone); it
    # goes electrically inert after the RDP/OTP lockdown at the end of stage 1.
    _net(d, "COMP_SWDCLK").connect(mpu.pin("JTCK-SWCLK"))   # SWCLK
    _net(d, "COMP_SWDIO") .connect(mpu.pin("JTMS-SWDIO"))   # SWDIO
    _net(d, "SWO")        .connect(mpu.pin("JTDO-TRACESWO"))
    _net(d, "NRST")       .connect(mpu.pin("NRST"))
    _net(d, "BOOT0")      .connect(mpu.pin("BOOT0"))        # force serial boot
    _net(d, "GND").connect(mpu.pin("BOOT1"))   # boot-mode straps — defined low;
    _net(d, "GND").connect(mpu.pin("BOOT2"))   # the OTP overrides boot device
    _net(d, "GND").connect(mpu.pin("BOOT3"))   # after provisioning.
    res_between(d, "COMP_3V3", "NRST", "10k", ref="R_MPU_NRST", board_tag=BTAG)
    cap_to_gnd(d, "NRST", "100nF", ref="C_MPU_NRST", board_tag=BTAG)
    res_between(d, "GND", "BOOT0", "10k", ref="R_MPU_BOOT0", board_tag=BTAG)

    # Bulk decoupling on supply rails
    cap_to_gnd(d, "COMP_5V",  "10uF",  ref="C_MPU_5V",   board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V",  "100nF", ref="C_MPU_5V2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_3V3", "10uF",  ref="C_MPU_33",   board_tag=BTAG)
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_MPU_33b",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── DDR4 (SMARTsemi KTDM4G4B626BGIEAT, FBGA-96; 1.2 V + VPP 2.5 V) ─
    # Swapped in for the AS4C DDR3L. DQ bus follows the ST AN5724 DDR4 reference
    # swizzle (see below); the A/C bus follows the ST DDR4 reference mapping
    # VERBATIM (Research/STM32MP25xxAx/STM32MP25xxAL/1DDR4_Memory_length_
    # equalization…AL (10x10)_Template.xlsx, BALL NAME → NET NAME columns —
    # AL/VFBGA-361 = our DAL3 package). The earlier DDR3L-derived guess is
    # gone; see the MPU-side block below for the locked table.
    ddr = add_ktdm4g4b626bgieat(d, ref="U_DDR4", board_tag=BTAG)

    # DQ swizzle = ST AN5724 DDR4 reference verbatim (STM32MP25xxAL "with
    # DDR4", Sheet 6 — AL/VFBGA-361 = our DAL3 package). A WITHIN-BYTE bit
    # permutation, hardware-transparent (the DDR4 PHY deskews each DQ bit;
    # DM masks per-byte, DBI inverts per-byte — so bit order inside a lane
    # is free). Kept VERBATIM deliberately: the reference's routed escape/
    # corridor topology (CAD_Project ascii PcbDoc) is co-designed with this
    # swizzle, and smash.layout.ddr_route mines that topology — re-swizzling
    # for our corridor would invalidate it. DRAM byte-pin DQL{m}/DQU{m} <-
    # controller DDR4_DQ{n}:
    _DQL_FROM = [7, 0, 6, 2, 5, 1, 4, 3]        # DQL0..7 <- DQ7,0,6,2,5,1,4,3
    _DQU_FROM = [15, 9, 12, 10, 14, 11, 13, 8]  # DQU0..7 <- DQ15,9,12,10,14,11,13,8

    # Data byte 0 (lower)
    for m, n in enumerate(_DQL_FROM):
        _net(d, f"DDR4_DQ{n}").connect(ddr.pin(f"DQL{m}"))
    _net(d, "DDR4_DQS0_T").connect(ddr.pin("DQSL_T"))
    _net(d, "DDR4_DQS0_C").connect(ddr.pin("DQSL_C"))
    _net(d, "DDR4_DM0_N") .connect(ddr.pin("DML_NDBIL_N"))

    # Data byte 1 (upper)
    for m, n in enumerate(_DQU_FROM):
        _net(d, f"DDR4_DQ{n}").connect(ddr.pin(f"DQU{m}"))
    _net(d, "DDR4_DQS1_T").connect(ddr.pin("DQSU_T"))
    _net(d, "DDR4_DQS1_C").connect(ddr.pin("DQSU_C"))
    _net(d, "DDR4_DM1_N") .connect(ddr.pin("DMU_NDBIU_N"))

    # Address A0..A13 (A10/AP, A12/BC_n are mux pins). Address-bit names
    # A1..A9 collide with the row-A ball coords; the factory BALL_-prefixes
    # those balls, so `ddr.pin("A1")` resolves to the address-bit pin.
    for i in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13]:
        _net(d, f"DDR4_A{i}").connect(ddr.pin(f"A{i}"))
    _net(d, "DDR4_A10").connect(ddr.pin("A10/AP"))
    _net(d, "DDR4_A12").connect(ddr.pin("A12/BC_N"))

    # Command + muxed upper address: ACT_n low → RAS/CAS/WE, ACT_n high →
    # A16/A15/A14.
    _net(d, "DDR4_ACT_N")    .connect(ddr.pin("ACT_N"))
    _net(d, "DDR4_RAS_N_A16").connect(ddr.pin("RAS_N/A16"))
    _net(d, "DDR4_CAS_N_A15").connect(ddr.pin("CAS_N/A15"))
    _net(d, "DDR4_WE_N_A14") .connect(ddr.pin("WE_N/A14"))

    # Bank group (x16 has BG0 only) + bank address
    _net(d, "DDR4_BG0").connect(ddr.pin("BG0"))
    _net(d, "DDR4_BA0").connect(ddr.pin("BA0"))
    _net(d, "DDR4_BA1").connect(ddr.pin("BA1"))

    # Clock + control
    _net(d, "DDR4_CK_T")   .connect(ddr.pin("CK_T"))
    _net(d, "DDR4_CK_C")   .connect(ddr.pin("CK_C"))
    _net(d, "DDR4_CKE")    .connect(ddr.pin("CKE"))
    _net(d, "DDR4_CS_N")   .connect(ddr.pin("CS_N"))
    _net(d, "DDR4_ODT")    .connect(ddr.pin("ODT"))
    _net(d, "DDR4_RESET_N").connect(ddr.pin("RESET_N"))
    res_between(d, "DDR4_RESET_N", "GND", "10k",
                ref="R_DDR_RESETN_PD", board_tag=BTAG)

    # DDR4 extras: ALERT_n → MP25 GPIO (monitored) + pull-up; PAR (C/A
    # parity) is WIRED per the EE reference layout (MPU DDR_A9/E18 →
    # DRAM PAR/T3) but stays disabled in MR5 — firmware must never
    # enable CA parity (ALERT_N reader is blind, rule-sweep F3); TEN
    # (connectivity test) tied low.
    _net(d, "DDR4_ALERT_N").connect(ddr.pin("ALERT_N"))
    # ALERT_N is a VDDQ-domain open-drain output (abs max ≈ VDDQ+0.3 V)
    # — the 1.2 V pull rail is mandatory. ⚠ rule-sweep F3: its MP25
    # reader PG12 is a TT input on a 3.3 V VDDIO bank (VIH ≈ 2.3 V), so
    # a 1.2 V high can never register. FIRMWARE: never enable DDR4 CA
    # parity / write-CRC — the only ALERT_N sources; the GPIO is dead.
    res_between(d, "DDR4_ALERT_N", "COMP_1V2", "10k",
                ref="R_DDR_ALERTN_PU", board_tag=BTAG)
    _net(d, "DDR4_PAR").connect(ddr.pin("PAR"))
    _net(d, "GND").connect(ddr.pin("TEN"))

    # VREFCA (external divider; DDR4 VREFDQ is internal) + ZQ calibration
    _net(d, "DDR4_VREFCA").connect(ddr.pin("VREFCA"))
    _net(d, "DDR4_ZQ_CAL").connect(ddr.pin("ZQ"))

    # DDR4 power: VDD/VDDQ = 1.2 V (COMP_1V2), VPP = 2.5 V (COMP_VPP — the
    # PMIC BUCK3 freed by dropping the DDR3L 1.35 V rail, retuned to 2.5 V)
    for n in range(1, 11): _net(d, "COMP_1V2").connect(ddr.pin(f"VDD_{n}"))
    for n in range(1, 11): _net(d, "COMP_1V2").connect(ddr.pin(f"VDDQ_{n}"))
    for n in range(1, 3):  _net(d, "COMP_VPP").connect(ddr.pin(f"VPP_{n}"))
    for n in range(1, 10): _net(d, "GND").connect(ddr.pin(f"VSS_{n}"))
    for n in range(1, 11): _net(d, "GND").connect(ddr.pin(f"VSSQ_{n}"))

    # ── MPU-side DDR4 wiring ──────────────────────────────────────────
    # Data + DQS + DM (1:1; DDR4 byte 0 = DQL, byte 1 = DQU)
    for i in range(16):
        _net(d, f"DDR4_DQ{i}").connect(mpu.pin(f"DDR_DQ{i}"))
    _net(d, "DDR4_DQS0_T").connect(mpu.pin("DDR_DQS0P"))
    _net(d, "DDR4_DQS0_C").connect(mpu.pin("DDR_DQS0N"))
    _net(d, "DDR4_DQS1_T").connect(mpu.pin("DDR_DQS1P"))
    _net(d, "DDR4_DQS1_C").connect(mpu.pin("DDR_DQS1N"))
    _net(d, "DDR4_DM0_N") .connect(mpu.pin("DDR_DQM0"))
    _net(d, "DDR4_DM1_N") .connect(mpu.pin("DDR_DQM1"))

    # A/C mapping — EE REFERENCE LAYOUT swizzle (siniziacompanion_compute,
    # imported via tools/import_ee_layout.py). The combo-PHY DDR_Ax balls
    # are generic; the PHY-signal→ball map is firmware-configurable, and
    # the EE re-swizzled 18 A/C balls (vs the ST AL template) to fit his
    # escape pattern, bringing DDR_A27 (L19, BG1 in the ST personality)
    # into service for ACT_n and DDR_A9 (E18) for PAR. Unchanged from the
    # ST template: CKE/CS_n/ODT/CK_T/CK_C (DDR_A0/A2/A3/A4/A5),
    # A3→DDR_A16, A9→DDR_A18, BA1→DDR_A29. FIRMWARE: the DDR tool /
    # PHY config must encode this map.
    A_MAP = {0: 20, 1: 10, 2: 17, 3: 16, 4: 26, 5: 21, 6: 30,
             7: 22, 8: 28, 9: 18, 10: 8, 11: 25, 12: 31, 13: 23}
    for i, mpu_a in A_MAP.items():
        _net(d, f"DDR4_A{i}").connect(mpu.pin(f"DDR_A{mpu_a}"))

    # Command + muxed upper address (EE reference: RASN→DDR_A11,
    # CASN→DDR_A15, WEN→DDR_A14, ACTN→DDR_A27, BG0→DDR_A12,
    # BA0→DDR_A13, PAR→DDR_A9).
    _net(d, "DDR4_RAS_N_A16").connect(mpu.pin("DDR_A11"))
    _net(d, "DDR4_CAS_N_A15").connect(mpu.pin("DDR_A15"))
    _net(d, "DDR4_WE_N_A14") .connect(mpu.pin("DDR_A14"))
    _net(d, "DDR4_ACT_N")    .connect(mpu.pin("DDR_A27"))
    _net(d, "DDR4_BG0")      .connect(mpu.pin("DDR_A12"))
    _net(d, "DDR4_BA0")      .connect(mpu.pin("DDR_A13"))
    _net(d, "DDR4_BA1")      .connect(mpu.pin("DDR_A29"))
    _net(d, "DDR4_PAR")      .connect(mpu.pin("DDR_A9"))

    # Clock + control (unchanged from the DDR3L reference — the DDR4
    # template keeps them on the same balls)
    _net(d, "DDR4_CK_T").connect(mpu.pin("DDR_A4"))
    _net(d, "DDR4_CK_C").connect(mpu.pin("DDR_A5"))
    _net(d, "DDR4_CKE") .connect(mpu.pin("DDR_A0"))
    _net(d, "DDR4_CS_N").connect(mpu.pin("DDR_A2"))
    _net(d, "DDR4_ODT") .connect(mpu.pin("DDR_A3"))

    # ALERT_n → MP25 PG12 — placeholder tie only: PG12 is TT on a 3.3 V
    # bank, blind to the 1.2 V swing (rule-sweep F3, disposition "never
    # enable CA parity"). Level-shift (BSS138) if alert telemetry is
    # ever wanted.
    try:
        _net(d, "DDR4_ALERT_N").connect(mpu.pin("PG12"))
    except KeyError:
        pass

    # Reset + VREFCA
    _net(d, "DDR4_RESET_N").connect(mpu.pin("DDR_RESETN"))
    _net(d, "DDR4_VREFCA") .connect(mpu.pin("DDR_VREF"))

    # MPU-side ZQ decoupling
    try:
        _net(d, "MPU_DDR_ZQ").connect(mpu.pin("DDR_ZQ"))
        cap_to_gnd(d, "MPU_DDR_ZQ", "0.1uF", ref="C_MPU_DDR_ZQ",
                   board_tag=BTAG)
    except KeyError:
        pass

    # DDR4 calibration + VREFCA generation (VREFDQ is internal on DDR4)
    res_between(d, "DDR4_ZQ_CAL", "GND", "240", ref="R_DDR_ZQ", board_tag=BTAG)
    res_between(d, "COMP_1V2", "DDR4_VREFCA", "1k",
                ref="R_DDR_VREFCA_TOP", board_tag=BTAG)
    res_between(d, "DDR4_VREFCA", "GND", "1k",
                ref="R_DDR_VREFCA_BOT", board_tag=BTAG)
    cap_to_gnd(d, "DDR4_VREFCA", "100nF", ref="C_DDR_VREFCA", board_tag=BTAG)

    # DDR4 power decoupling: 1.2 V rail (6× per-ball 100 nF ECM + 2× 10 µF
    # bulk) + VPP 2.5 V (1 µF + 100 nF).
    for n in range(1, 7):
        cap_to_gnd(d, "COMP_1V2", "100nF", ref=f"C_DDR_VDD{n}",
                   embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2", "10uF", ref="C_DDR_BULK1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2", "10uF", ref="C_DDR_BULK2", board_tag=BTAG)
    cap_to_gnd(d, "COMP_VPP", "1uF",   ref="C_DDR_VPP1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_VPP", "100nF", ref="C_DDR_VPP2", board_tag=BTAG)


def build_radar_module(d: Design) -> None:
    """AWR2944 77 GHz FMCW radar SoC + 1.0V buck (LMR10510) + 1.8V LDO
    (LDL112PV18R). Host link is SPI to the MP25 Cortex-M33 (also its host-SPI
    boot path — the radar has no local flash, RAM-loaded every power-up). The
    image is streamed ENCRYPTED: the AWR HSM secure-boot (TI HS-SE, AES-256
    with the customer MEK + MPK signature, keys in the AWR eFuses) decrypts +
    verifies it in-radar, so plaintext never crosses the SPI wire — see
    firmware_lifecycle.md. The buck + LDO tap always-on BAT_PROT directly and
    self-gate via their EN pins (RADAR_EN, M33 PE10) — no discrete load switch;
    a 100k pull-down keeps the radar OFF when the M33 is unpowered."""
    BTAG = "radar_module"

    # ── 1.0V buck (LMR10510XMFE/NOPB, SOT-23-5) ─────────────────────
    buck = add_lmr10510xmfe_nopb(d, ref="U_AWR_BUCK", board_tag=BTAG)
    _net(d, "BAT_PROT")  .connect(buck.pin("VIN"))   # always-on tap (no load switch)
    _net(d, "GND")       .connect(buck.pin("GND"))
    _net(d, "AWR_1V0_SW").connect(buck.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck.pin("EN"))    # M33-gated via the reg EN
    _net(d, "AWR_1V0_FB").connect(buck.pin("FB"))
    # Radar power: the buck + LDO tap always-on BAT_PROT and self-gate via their
    # EN pins tied to RADAR_EN (M33 PE10) — no upstream FET. The 100k pull-down
    # keeps both regulators OFF (radar unpowered) whenever the M33 is unpowered
    # (shelf/standby); RADAR_EN's 3V3 logic-high clears the EN thresholds
    # (≥1.4 V), which is what the old BSS138 level-shifter existed for.
    res_between(d, "RADAR_EN", "GND", "100k", ref="R_RADAR_EN_PD", board_tag=BTAG)

    # system.py uses L_0402 for the AWR buck inductor (Wurth WE-KI
    # family goes up to 22 µH in 0402 even though smash's auto-
    # dispatch is conservative — force the family explicitly).
    ind_between(d, "AWR_1V0_SW", "AWR_1V0", "4.7uH",
                ref="L_AWR_BUCK", family="we-ki", board_tag=BTAG)
    res_between(d, "AWR_1V0",    "AWR_1V0_FB", "30k",
                ref="R_AWR_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V0_FB", "GND",        "100k",
                ref="R_AWR_FB2", board_tag=BTAG)

    cap_to_gnd(d, "BAT_PROT", "10uF",  ref="C_AWR_BUCK_IN1", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "100nF", ref="C_AWR_BUCK_IN2", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V0",   "22uF",  ref="C_AWR_1V0_1",    board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V0",   "100nF", ref="C_AWR_1V0_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── 1.8V LDO ────────────────────────────────────────────────────
    ldo18 = add_ldl112pv18r(d, ref="U_AWR_LDO18", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(ldo18.pin("VIN"))
    _net(d, "GND")     .connect(ldo18.pin("GND"))
    _net(d, "RADAR_EN").connect(ldo18.pin("EN"))
    _net(d, "AWR_1V8")  .connect(ldo18.pin("VOUT"))
    _net(d, "GND")      .connect(ldo18.pin("EP"))   # per DS10321 Table 1: EP must be GND

    cap_to_gnd(d, "AWR_1V8", "10uF",  ref="C_AWR_1V8_1", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── AWR2944 ─────────────────────────────────────────────────────
    awr = add_awr2944abgaltrq1(d, ref="U_AWR", board_tag=BTAG)

    # 1.0V digital + RF analog
    for n in range(1, 18):  _net(d, "AWR_1V0").connect(awr.pin(f"VDD_{n}"))
    _net(d, "AWR_1V0").connect(awr.pin("VDD_SRAM"))
    _net(d, "AWR_1V0").connect(awr.pin("VDDA_10RF2_1"))
    _net(d, "AWR_1V0").connect(awr.pin("VDDA_10RF2_2"))
    _net(d, "AWR_1V0").connect(awr.pin("VIDDA__10RF1"))

    # 1.8V analog + I/O
    for nm in ("VDDA_18BB", "VDDA_18CLK", "VDDA_18PM", "VDDA_18VCO",
               "VIOIN__18CSI", "VIOIN__18LVDS"):
        _net(d, "AWR_1V8").connect(awr.pin(nm))
    for n in range(1, 4):  _net(d, "AWR_1V8").connect(awr.pin(f"VIOIN_18_{n}"))
    for n in range(1, 6):  _net(d, "AWR_1V8").connect(awr.pin(f"VIOIN_{n}"))

    # Internal-regulator decoupling
    _net(d, "VBGAP")        .connect(awr.pin("VBGAP"))
    _net(d, "VOUT__14APLL") .connect(awr.pin("VOUT__14APLL"))
    _net(d, "VOUT__14SYNTH").connect(awr.pin("VOUT__14SYNTH"))
    cap_to_gnd(d, "VBGAP",         "100nF", ref="C_AWR_VBGAP",   board_tag=BTAG)
    cap_to_gnd(d, "VOUT__14APLL",  "100nF", ref="C_AWR_14APLL",  board_tag=BTAG)
    cap_to_gnd(d, "VOUT__14SYNTH", "100nF", ref="C_AWR_14SYNTH", board_tag=BTAG)

    # Substrate + VPP to GND
    _net(d, "GND").connect(awr.pin("VNWA"))
    _net(d, "GND").connect(awr.pin("VPP"))

    # All grounds — iterate VSS_1..69 + VSSA_1..52, skip any not present
    for n in range(1, 70):
        try:
            _net(d, "GND").connect(awr.pin(f"VSS_{n}"))
        except KeyError:
            break
    for n in range(1, 53):
        try:
            _net(d, "GND").connect(awr.pin(f"VSSA_{n}"))
        except KeyError:
            break

    # Signal pins
    _net(d, "AWR_NRESET")  .connect(awr.pin("NRESET"))
    _net(d, "AWR_FAULT")   .connect(awr.pin("NERROR_OUT"))
    _net(d, "AWR_SPI_CS")  .connect(awr.pin("MSS_MIBSPIA__~{CS0}"))
    _net(d, "AWR_SPI_CLK") .connect(awr.pin("MSS_MIBSPIA__CLK"))
    _net(d, "AWR_SPI_MOSI").connect(awr.pin("MSS_MIBSPIA__MOSI"))
    _net(d, "AWR_SPI_MISO").connect(awr.pin("MSS_MIBSPIA__MISO"))

    # Gigabit Ethernet (CPSW RGMII) → MP25 GMAC, MAC-to-MAC (no PHY/magnetics).
    # The AWR's TX pairs to the MP25's RX and vice-versa (crossed). MDIO unused
    # (fixed-link). This is the radar data path (range-Doppler frames to the NPU).
    for net, pin in (
        # MP25 TX → AWR RX
        ("RAD_ETH_TXD0", "MSS_RGMII__RD0"),   ("RAD_ETH_TXD1", "MSS_RGMII__RD1"),
        ("RAD_ETH_TXD2", "MSS_RGMII__RD2"),   ("RAD_ETH_TXD3", "MSS_RGMII__RD3"),
        ("RAD_ETH_TX_CTL", "MSS_RGMII__RCTL"),("RAD_ETH_TXC", "MSS_RGMII__RCLK"),
        # AWR TX → MP25 RX
        ("RAD_ETH_RXD0", "MSS_RGMII__TD0"),   ("RAD_ETH_RXD1", "MSS_RGMII__TD1"),
        ("RAD_ETH_RXD2", "MSS_RGMII__TD2"),   ("RAD_ETH_RXD3", "MSS_RGMII__TD3"),
        ("RAD_ETH_RX_CTL", "MSS_RGMII__TCTL"),("RAD_ETH_RXC", "MSS_RGMII__TCLK"),
    ):
        _net(d, net).connect(awr.pin(pin))
    # MCAN unused — the radar's host link is SPI (MSS_MIBSPIA, above), which is
    # also its host-SPI boot interface (SOP=1). CAN-FD removed system-wide.
    _net(d, "AWR_TX0").connect(awr.pin("TX1"))
    _net(d, "AWR_TX1").connect(awr.pin("TX2"))
    _net(d, "AWR_TX2").connect(awr.pin("TX3"))
    _net(d, "AWR_RX0").connect(awr.pin("RX1"))
    _net(d, "AWR_RX1").connect(awr.pin("RX2"))
    _net(d, "AWR_RX2").connect(awr.pin("RX3"))
    _net(d, "AWR_RX3").connect(awr.pin("RX4"))

    # SOP boot-mode (5 pins, mapped to SamacSys post-boot signal names)
    _net(d, "AWR_SOP0").connect(awr.pin("TDO"))
    _net(d, "AWR_SOP1").connect(awr.pin("MSS_MIBSPIB__CS2"))
    _net(d, "AWR_SOP2").connect(awr.pin("PMIC_CLKOUT"))
    _net(d, "AWR_SOP3").connect(awr.pin("MSS_UARTB__TX"))
    _net(d, "AWR_SOP4").connect(awr.pin("MSS_UARTA__TX"))

    # Reset pull-up + filter; fault pull-up; SOP bias resistors
    res_between(d, "AWR_1V8", "AWR_NRESET", "10k",
                ref="R_AWR_NRST",     board_tag=BTAG)
    cap_to_gnd(d, "AWR_NRESET", "100nF", ref="C_AWR_NRST", board_tag=BTAG)
    res_between(d, "3V3",     "AWR_FAULT",  "100k",
                ref="R_AWR_FAULT_PU", board_tag=BTAG)
    res_between(d, "AWR_1V8", "AWR_SOP0", "10k", ref="R_AWR_SOP0", board_tag=BTAG)
    res_between(d, "AWR_SOP1","GND",      "10k", ref="R_AWR_SOP1", board_tag=BTAG)
    res_between(d, "AWR_SOP2","GND",      "10k", ref="R_AWR_SOP2", board_tag=BTAG)
    res_between(d, "AWR_SOP3","GND",      "10k", ref="R_AWR_SOP3", board_tag=BTAG)
    res_between(d, "AWR_SOP4","GND",      "10k", ref="R_AWR_SOP4", board_tag=BTAG)

    # CAN-FD transceiver removed — the radar talks to the MP25 M33 over SPI
    # (MSS_MIBSPIA), which doubles as its host-SPI boot/flash path.


def build_radar_module_awr2e44p(d: Design) -> None:
    """Forward-end variant of build_radar_module using the **AWR2E44P** instead
    of the AWR2944. Same power tree (1.0 V buck + 1.8 V LDO off BAT_PROT, M33-
    gated via RADAR_EN), same SPI host link + RGMII data path to the MP25 — but
    three things change with the rearchitecture:

      1. NO discrete TX/RX antenna pins. The AWR2E44P couples 77 GHz into the
         machined aluminium waveguide/horn block via on-package SIW launches
         (`VDDA_10RF*` rails), so the AWR2944's TX1-3/RX1-4 balls simply don't
         exist — there is nothing to wire to the laminate. (This is also why
         the radar board dropped Rogers for plain FR4: the PCB never sees RF.)
      2. The SoC is 13.5×12 mm FCCSP, 278-ball — a different footprint, wired
         here from the EVM-lifted ballmap (see add_awr2e44pbgamxrq1).
      3. The pin naming follows the EVM ballmap (single-underscore, ball-unique)
         rather than the AWR2944 SamacSys symbol, so rails are gathered with
         `pins_by_name()` (e.g. 127× VSSA) and signals resolved by name.

    NOT wired into the live netlist yet — build_radar_module (AWR2944) is still
    the active radar. Swap the call in build_design() to switch the forward end
    to the AWR2E44P once the castellated USB/LED block + FR4 stack land.

    DATASHEET CAVEATS (cross-ref awr2944p_family.pdf before fab):
      • VIO domain: the EVM runs the bare `VIOIN` rail at 3.3 V (net 3V3_VIO).
        We tie it to AWR_1V8 to match the AWR2944 baseline + the MP25 host bank;
        confirm the MP25 GMAC/SPI bank voltage and flip to 3V3 if needed.
      • SOP boot straps: SOP0=TDO, SOP2=PMIC_CLKOUT, SOP4=MSS_UARTA_TX are
        EVM-confirmed (FUNC/host-SPI = SOP[2:0]=001, 40 MHz xtal = SOP[4:3]=00).
        SOP1/SOP3 ride muxed functions (MSS_SPIB_CS2 / MSS_UARTB_TX) that the
        lifted ballmap doesn't break out — set those balls + the exact bias
        resistor values per the datasheet boot table.
      • 40 MHz reference (CLKP/CLKM xtal or driven XREF_CLK0) is left open here,
        exactly as build_radar_module leaves the AWR2944 clock — add it system-
        wide when the clocking is finalized."""
    BTAG = "radar_module"

    # ── Power tree (identical to the AWR2944 build: 1.0 V buck + 1.8 V LDO,
    #    both tapping always-on BAT_PROT and self-gating via RADAR_EN) ──────
    buck = add_lmr10510xmfe_nopb(d, ref="U_AWR_BUCK", board_tag=BTAG)
    _net(d, "BAT_PROT")  .connect(buck.pin("VIN"))
    _net(d, "GND")       .connect(buck.pin("GND"))
    _net(d, "AWR_1V0_SW").connect(buck.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck.pin("EN"))
    _net(d, "AWR_1V0_FB").connect(buck.pin("FB"))
    res_between(d, "RADAR_EN", "GND", "100k", ref="R_RADAR_EN_PD", board_tag=BTAG)
    ind_between(d, "AWR_1V0_SW", "AWR_1V0", "4.7uH",
                ref="L_AWR_BUCK", family="we-ki", board_tag=BTAG)
    res_between(d, "AWR_1V0",    "AWR_1V0_FB", "30k",
                ref="R_AWR_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V0_FB", "GND",        "100k",
                ref="R_AWR_FB2", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "10uF",  ref="C_AWR_BUCK_IN1", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "100nF", ref="C_AWR_BUCK_IN2", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V0",   "22uF",  ref="C_AWR_1V0_1",    board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V0",   "100nF", ref="C_AWR_1V0_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    ldo18 = add_ldl112pv18r(d, ref="U_AWR_LDO18", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(ldo18.pin("VIN"))
    _net(d, "GND")     .connect(ldo18.pin("GND"))
    _net(d, "RADAR_EN").connect(ldo18.pin("EN"))
    _net(d, "AWR_1V8")  .connect(ldo18.pin("VOUT"))
    _net(d, "GND")      .connect(ldo18.pin("EP"))
    cap_to_gnd(d, "AWR_1V8", "10uF",  ref="C_AWR_1V8_1", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── AWR2E44P ────────────────────────────────────────────────────────────
    awr = add_awr2e44pbgamxrq1(d, ref="U_AWR", board_tag=BTAG)

    def _rail(net, *names):
        """Tie every ball carrying any of `names` to `net` (handles the
        many-balls-per-rail case, e.g. 16× VDD / 127× VSSA)."""
        for nm in names:
            balls = awr.pins_by_name(nm)
            if not balls:
                raise KeyError(f"AWR2E44P: no ball named {nm!r}")
            for p in balls:
                _net(d, net).connect(p)

    # 1.0 V — digital core + SRAM + RF analog (the SIW-launch supplies)
    _rail("AWR_1V0", "VDD", "VDD_SRAM", "VDDA_10RF1", "VDDA_10RF2")
    # 1.8 V — analog (baseband/VCO), PM input, LVDS/CSI + clock I/O
    _rail("AWR_1V8", "VDDA_18BB", "VDDA_18VCO", "VIN_18PM",
          "VIOIN_18", "VIOIN_18LVDS", "VIOIN_18CLK")
    # VIO domain — run at 1.8 V to match the AWR2944 baseline + MP25 host bank
    # (the EVM runs this 3V3_VIO; see the docstring caveat).
    _rail("AWR_1V8", "VIOIN")

    # Internal-regulator outputs — decouple to GND, never driven
    for net, ball in (("VBGAP", "VBGAP"),
                      ("VOUT_14APLL", "VOUT_14APLL"),
                      ("VOUT_14SYNTH", "VOUT_14SYNTH")):
        _net(d, net).connect(awr.pin(ball))
    cap_to_gnd(d, "VBGAP",        "100nF", ref="C_AWR_VBGAP",   board_tag=BTAG)
    cap_to_gnd(d, "VOUT_14APLL",  "100nF", ref="C_AWR_14APLL",  board_tag=BTAG)
    cap_to_gnd(d, "VOUT_14SYNTH", "100nF", ref="C_AWR_14SYNTH", board_tag=BTAG)

    # Grounds (VSSA ×127 + VSS ×22) + substrate (VNWA) + VPP (tie GND when not
    # one-time-programming, per the AWR2944 build)
    _rail("GND", "VSSA", "VSS", "VNWA", "VPP")

    # Reset / fault — active-low balls carry KiCad overbar escaping in the
    # lifted ballmap (R\E\S\E\T\, E\R\R\O\R\_\O\U\T\), so resolve them by ball.
    _net(d, "AWR_NRESET").connect(awr.pin("C19"))   # R\E\S\E\T\
    _net(d, "AWR_FAULT") .connect(awr.pin("B6"))    # E\R\R\O\R\_\O\U\T\
    res_between(d, "AWR_1V8", "AWR_NRESET", "10k", ref="R_AWR_NRST", board_tag=BTAG)
    cap_to_gnd(d, "AWR_NRESET", "100nF", ref="C_AWR_NRST", board_tag=BTAG)
    res_between(d, "3V3", "AWR_FAULT", "100k", ref="R_AWR_FAULT_PU", board_tag=BTAG)

    # Host link — MSS_MIBSPIA to the MP25 M33 (also the host-SPI boot path)
    _net(d, "AWR_SPI_CS")  .connect(awr.pin("MSS_MIBSPIA_CS0"))
    _net(d, "AWR_SPI_CLK") .connect(awr.pin("MSS_MIBSPIA_CLK"))
    _net(d, "AWR_SPI_MOSI").connect(awr.pin("MSS_MIBSPIA_MOSI"))
    _net(d, "AWR_SPI_MISO").connect(awr.pin("MSS_MIBSPIA_MISO"))

    # Gigabit Ethernet (CPSW RGMII) → MP25 GMAC, MAC-to-MAC, crossed (TX↔RX),
    # same data path as the AWR2944 build (range-Doppler frames to the NPU).
    for net, pin in (
        ("RAD_ETH_TXD0", "MSS_RGMII_RD0"),   ("RAD_ETH_TXD1", "MSS_RGMII_RD1"),
        ("RAD_ETH_TXD2", "MSS_RGMII_RD2"),   ("RAD_ETH_TXD3", "MSS_RGMII_RD3"),
        ("RAD_ETH_TX_CTL", "MSS_RGMII_RCTL"),("RAD_ETH_TXC", "MSS_RGMII_RCLK"),
        ("RAD_ETH_RXD0", "MSS_RGMII_TD0"),   ("RAD_ETH_RXD1", "MSS_RGMII_TD1"),
        ("RAD_ETH_RXD2", "MSS_RGMII_TD2"),   ("RAD_ETH_RXD3", "MSS_RGMII_TD3"),
        ("RAD_ETH_RX_CTL", "MSS_RGMII_TCTL"),("RAD_ETH_RXC", "MSS_RGMII_TCLK"),
    ):
        _net(d, net).connect(awr.pin(pin))

    # SOP boot straps — FUNC / host-SPI boot (SOP[2:0]=001), 40 MHz (SOP[4:3]=00).
    # Only the EVM-confirmed straps are wired; SOP1/SOP3 ride muxed functions the
    # lifted ballmap doesn't expose (see docstring). Bias values per datasheet.
    _net(d, "AWR_SOP0").connect(awr.pin("TDO"))          # SOP0
    _net(d, "AWR_SOP2").connect(awr.pin("PMIC_CLKOUT"))  # SOP2 (EVM SOP2_PMIC_CLK)
    _net(d, "AWR_SOP4").connect(awr.pin("MSS_UARTA_TX")) # SOP4 (EVM SOP4_MSS_UARTA_TX)
    res_between(d, "AWR_1V8", "AWR_SOP0", "10k", ref="R_AWR_SOP0", board_tag=BTAG)
    res_between(d, "AWR_SOP2", "GND",     "10k", ref="R_AWR_SOP2", board_tag=BTAG)
    res_between(d, "AWR_SOP4", "GND",     "10k", ref="R_AWR_SOP4", board_tag=BTAG)

    # Spare/debug/clock balls (CLKP/CLKM, XREF_CLK0, GPIO, I2C, MCAN, QSPI,
    # MDIO, CSI2, LVDS_TX, ADC, MIBSPIB, UART RX, RS232, WARM_RESET) are left
    # unconnected — not used in the radar role, matching the AWR2944 build.


def build_radar_module_awr1843aop(d: Design) -> None:
    """Forward-end variant using the **AWR1843AOP** (Antennas-On-Package).

    Third radar option after build_radar_module (AWR2944 — discrete TX/RX
    balls → external antenna) and build_radar_module_awr2e44p (waveguide
    launches → horn block). Here the 3 TX + 4 RX patches are ON the package,
    so — like the AWR2E44P — there are NO antenna balls and NO RF on the
    laminate; the nose_cap becomes an RF-transparent **radome**, not a
    machined block. See add_awr1843aop.

    Architecture (radar does its own detection): the AWR1843's C674x DSP +
    Radar HWA + Cortex-R4F run the detection chain ON-CHIP (range/Doppler
    FFT, CFAR, AoA) and emit a point cloud / object list to the MP25 over
    **SPIA**, with a data-ready interrupt (SPI_HOST_INTR). The radar
    communicates *detections*, not raw frames — so the AWR2944/2E44P gigabit
    RGMII data path is dropped.

    Boot DIFFERS from the AWR2944: the AWR1843AOP has no host-SPI-to-RAM boot —
    it boots its application from a local **QSPI flash** (datasheet §6.10.12;
    "autonomous mode"). So this build adds an S25HL512T QSPI NOR. The image is
    encrypted + signed and decrypted in-chip by the AoP HSM (secure boot), so
    plaintext firmware never persists at rest — the firmware_lifecycle.md rule
    holds; only the mechanism changes (local encrypted flash the MP25
    provisions, vs the AWR2944's MP25-streams-over-SPI). A 40 MHz reference
    (DSC1001CI5-040 oscillator → CLKP) is required for boot and is wired here.

    Power tree differs from the AWR2944/2E44P: the 1843's core is **1.2 V**
    (SWRS236 VDDIN/VIN_SRAM/VNWA — the 2944's was 1.0 V) and it adds
    **1.3 V** for the RF front-end (VIN_13RF). So: a 1.2 V buck + a 1.3 V
    buck (each LMR10510 + catch diode — the part is non-synchronous) + a
    1.8 V LDO, all off always-on BAT_PROT and self-gated via RADAR_EN. The
    EVM (AWR1843AOPEVM / SPRR449) uses one **LP87524-Q1** quad-buck PMIC for
    these rails — a future area-saving swap for the Ø34 sonde; kept discrete
    here to reuse the catalogue and match the other radar builds.

    DATASHEET STATUS (audited vs SWRS236C, 2026-06-10):
      • Rails set per ROC: 1.2 V core (100k/100k, VFB=0.6) incl. VNWA back
        bias; 1.3 V RF (118k/100k); VIOIN on COMP_3V3 (the TI EVM config —
        matches the MP25 host pins, which live in 3.3 V banks). The boot
        flash followed: SST26WF080B (1.8 V) → SST26VF080A (2.7-3.6 V),
        pin-compatible. Control/strap pull-ups all ride the VIOIN rail.
      • SOP straps wired 001 = functional/QSPI-flash boot; exact decode
        still to be confirmed against the TRM + EVM jumper defaults.
      • 40 MHz reference: DSC1001 square DC-coupled through 330/390 to
        ≈1.0 V per Table 6-6 (AC coupling is the sine-mode option).
      • VPP grounded = no in-system fuse programming (keys factory-fused)."""
    BTAG = "radar_module"

    # ── 1.2 V buck (LMR10510) — VDDIN core + SRAM + VNWA back-bias ──────────
    # SWRS236 rail: 1.2 V (1.14–1.32) — the previous 1.0 V target was an
    # AWR2944 leftover, and its 30k/100k divider actually made 0.78 V (the
    # LMR10510 reference is 0.600 V, not 0.8). 100k/100k → 1.200 V.
    buck12 = add_lmr10510xmfe_nopb(d, ref="U_AWR_BUCK12", feature="bottom", board_tag=BTAG)
    _net(d, "BAT_PROT")  .connect(buck12.pin("VIN"))
    _net(d, "GND")       .connect(buck12.pin("GND"))
    _net(d, "AWR_1V2_SW").connect(buck12.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck12.pin("EN"))
    _net(d, "AWR_1V2_FB").connect(buck12.pin("FB"))
    res_between(d, "RADAR_EN", "GND", "100k", ref="R_RADAR_EN_PD", board_tag=BTAG)
    # 2.2 µH TMS: ΔiL ≈ 0.32 A p-p @1.6 MHz → peak ≈ 0.6 A, inside the
    # LMR10510's 1.2 A limit and the TMS-2R2's Isat (the old binding was
    # a nonexistent "WE-KI 0402 4.7 µH" — an RF family capped ~120 nH).
    # The WHOLE buck cluster (U+L+D+caps) rides the BOTTOM
    # (companion-facing) face with the locked J_USB_C + its usb_zone
    # column owning the top NE: packer-placed L/D/C on the top face
    # ended up hugging the USB area (L13 at board (7.7,7.7)) and
    # dragging the nose-side cutout into it — and the SMC catch
    # diodes found no top slot at all (parked = the radar overflow).
    # Bottom south is open, and one face keeps the switch loop tight.
    ind_between(d, "AWR_1V2_SW", "AWR_1V2", "2.2uH",
                ref="L_AWR_BUCK12", feature="bottom", board_tag=BTAG)
    # Catch diode — the LMR10510 is NON-synchronous (DS pin table: SW
    # "connect to the inductor and catch diode"); without it the inductor
    # has no off-time path and the rail can't regulate.
    d_b12 = add_mbrs340t3g(d, ref="D_AWR_BUCK12", feature="bottom",
                           board_tag=BTAG)
    _net(d, "AWR_1V2_SW").connect(d_b12.pin("K"))
    _net(d, "GND")       .connect(d_b12.pin("A"))
    res_between(d, "AWR_1V2", "AWR_1V2_FB", "100k", ref="R_AWR12_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V2_FB", "GND", "100k", ref="R_AWR12_FB2", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V2", "22uF",  ref="C_AWR_1V2_1",
               feature="bottom", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V2", "100nF", ref="C_AWR_1V2_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── 1.3 V buck (LMR10510) — VIN_13RF RF supply ──────────────────────────
    # 118k/100k → 0.6×2.18 = 1.308 V (the old 68k/100k made 1.008 V).
    buck13 = add_lmr10510xmfe_nopb(d, ref="U_AWR_BUCK13", feature="bottom", board_tag=BTAG)
    _net(d, "BAT_PROT")  .connect(buck13.pin("VIN"))
    _net(d, "GND")       .connect(buck13.pin("GND"))
    _net(d, "AWR_1V3_SW").connect(buck13.pin("SW"))
    _net(d, "RADAR_EN")  .connect(buck13.pin("EN"))
    _net(d, "AWR_1V3_FB").connect(buck13.pin("FB"))
    ind_between(d, "AWR_1V3_SW", "AWR_1V3", "2.2uH",
                ref="L_AWR_BUCK13", feature="bottom",
                board_tag=BTAG)   # see L_AWR_BUCK12 note
    d_b13 = add_mbrs340t3g(d, ref="D_AWR_BUCK13", feature="bottom",
                           board_tag=BTAG)   # catch diode (see BUCK12)
    _net(d, "AWR_1V3_SW").connect(d_b13.pin("K"))
    _net(d, "GND")       .connect(d_b13.pin("A"))
    res_between(d, "AWR_1V3", "AWR_1V3_FB", "118k", ref="R_AWR13_FB1", board_tag=BTAG)
    res_between(d, "AWR_1V3_FB", "GND", "100k", ref="R_AWR13_FB2", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V3", "22uF",  ref="C_AWR_1V3_1",
               feature="bottom", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V3", "100nF", ref="C_AWR_1V3_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # Shared buck input decoupling on always-on BAT_PROT (bottom, at
    # the bucks' VIN — the 10 µF was landing on F.Cu dead-centre,
    # inside the U_AWR courtyard)
    cap_to_gnd(d, "BAT_PROT", "10uF",  ref="C_AWR_BUCK_IN1",
               feature="bottom", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "100nF", ref="C_AWR_BUCK_IN2",
               feature="bottom", board_tag=BTAG)

    # ── 1.8 V LDO (LDL112PV18R) — analog (BB/VCO/CLK) + I/O ──────────────────
    ldo18 = add_ldl112pv18r(d, ref="U_AWR_LDO18", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(ldo18.pin("VIN"))
    _net(d, "GND")     .connect(ldo18.pin("GND"))
    _net(d, "RADAR_EN").connect(ldo18.pin("EN"))
    _net(d, "AWR_1V8") .connect(ldo18.pin("VOUT"))
    _net(d, "GND")     .connect(ldo18.pin("EP"))
    cap_to_gnd(d, "AWR_1V8", "10uF",  ref="C_AWR_1V8_1", board_tag=BTAG)
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── AWR1843AOP ──────────────────────────────────────────────────────────
    # feature="rf": the AoP is the radiator → stays on the nose_cap-facing TOP
    # face. Only small/legged support opts to the bottom (the clock via
    # feature="clock", the SOT-23 bucks + boot flash via feature="bottom"); the
    # LDO + bulk caps stay on top, their cutouts merged by _mark_radar_block_cutout's
    # min-wall close. (Bulk caps kept top: too tall/heavy for the bottom envelope.)
    awr = add_awr1843aop(d, ref="U_AWR", secure=_RADAR_SECURE, board_tag=BTAG)

    def _tie(net, *bases):
        """Connect every ball named `base` or `base_<n>` (n=1..) to `net` —
        handles unnumbered (VPP, VBGAP) and numbered (VDDIN_1..5) rails alike.
        Raises if a base matches nothing (catches symbol drift)."""
        for base in bases:
            matched = False
            try:
                _net(d, net).connect(awr.pin(base)); matched = True
            except KeyError:
                pass
            n = 1
            while True:
                try:
                    _net(d, net).connect(awr.pin(f"{base}_{n}"))
                    matched = True; n += 1
                except KeyError:
                    break
            if not matched:
                raise KeyError(f"AWR1843AOP: no ball for rail base {base!r}")

    # 1.2 V — digital core + SRAM + SRAM array back bias (SWRS236: VNWA is a
    # 1.2 V POWER rail, 1.14–1.32 V recommended — NOT a ground tie)
    _tie("AWR_1V2", "VDDIN", "VIN_SRAM", "VNWA")
    # 1.3 V — RF front-end (TX PAs + RX)
    _tie("AWR_1V3", "VIN_13RF1", "VIN_13RF2")
    # 1.8 V — baseband / VCO / CLK analog + diff + 1.8 V I/O bank
    _tie("AWR_1V8", "VIN_18BB", "VIN_18VCO", "VIN_18CLK", "VIOIN_18", "VIOIN_18DIFF")
    # VIOIN general I/O domain — 3.3 V (the TI EVM configuration): the MP25
    # host pins for SPIA/IRQ/reset live in 3.3 V banks (VDDIO1/3 + VDD), so
    # the AWR's dual-voltage I/O domain matches them. COMP_3V3 extends one
    # gap (companion→radar) over the LGA lands. The VIOIN_18* balls above
    # stay on AWR_1V8 — that domain is fixed-1.8 V by the chip.
    _tie("COMP_3V3", "VIOIN")

    # Internal-regulator outputs — decouple to GND, never driven
    for net, base in (("VBGAP", "VBGAP"),
                      ("AWR_VOUT_14APLL", "VOUT_14APLL"),
                      ("AWR_VOUT_14SYNTH", "VOUT_14SYNTH"),
                      ("AWR_VOUT_PA", "VOUT_PA")):
        _tie(net, base)
    cap_to_gnd(d, "VBGAP",            "100nF", ref="C_AWR_VBGAP",   board_tag=BTAG)
    cap_to_gnd(d, "AWR_VOUT_14APLL",  "100nF", ref="C_AWR_14APLL",  board_tag=BTAG)
    cap_to_gnd(d, "AWR_VOUT_14SYNTH", "100nF", ref="C_AWR_14SYNTH", board_tag=BTAG)
    cap_to_gnd(d, "AWR_VOUT_PA",      "100nF", ref="C_AWR_VOUT_PA", board_tag=BTAG)

    # Grounds (VSS ×22 + VSSA ×53) + VPP (GND = no in-system OTP/fuse
    # programming — secure-boot keys must come factory-fused; provisioning-
    # flow decision, confirm vs TRM). VNWA moved to the 1.2 V tie above.
    _tie("GND", "VSS", "VSSA", "VPP")

    # ── Reset / fault ───────────────────────────────────────────────────────
    _net(d, "AWR_NRESET").connect(awr.pin("NRESET"))
    _net(d, "AWR_FAULT") .connect(awr.pin("NERROR_OUT"))
    # All control pull-ups ride the VIOIN-domain rail (COMP_3V3 — SWRS236
    # §5.3: the I/Os are non-failsafe, never pull above/without VIO; with
    # VIOIN at 3.3 V the straps must pull to 3.3 V to clear VIH = 0.7·VIO).
    res_between(d, "COMP_3V3", "AWR_NRESET", "10k", ref="R_AWR_NRST", board_tag=BTAG)
    cap_to_gnd(d, "AWR_NRESET", "100nF", ref="C_AWR_NRST", board_tag=BTAG)
    res_between(d, "COMP_3V3", "AWR_FAULT", "100k", ref="R_AWR_FAULT_PU", board_tag=BTAG)
    # error-in + warm-reset held inactive (pulled up to the VIOIN domain)
    _net(d, "AWR_NERR_IN") .connect(awr.pin("NERROR_IN"))
    _net(d, "AWR_WARM_RST").connect(awr.pin("WARM_RESET"))
    res_between(d, "COMP_3V3", "AWR_NERR_IN",  "10k", ref="R_AWR_NERRIN_PU",  board_tag=BTAG)
    res_between(d, "COMP_3V3", "AWR_WARM_RST", "10k", ref="R_AWR_WARMRST_PU", board_tag=BTAG)

    # ── Host link — SPIA to the MP25 M33 (detections out + host-SPI boot in) ──
    _net(d, "AWR_SPI_CS")  .connect(awr.pin("SPIA_CS_N"))
    _net(d, "AWR_SPI_CLK") .connect(awr.pin("SPIA_CLK"))
    _net(d, "AWR_SPI_MOSI").connect(awr.pin("SPIA_MOSI"))
    _net(d, "AWR_SPI_MISO").connect(awr.pin("SPIA_MISO"))
    _net(d, "AWR_DRDY")    .connect(awr.pin("SPI_HOST_INTR"))  # detections-ready IRQ → MP25 GPIO
    res_between(d, "COMP_3V3", "AWR_DRDY", "10k", ref="R_AWR_DRDY_PU", board_tag=BTAG)

    # ── 40 MHz reference clock (DSC1001CI5-040 MEMS oscillator) ──────────────
    # The AWR1843AOP requires an external 40 MHz reference for boot (datasheet
    # §6: "requires external clock source ... for initial boot"). External-clock
    # mode: drive CLKP single-ended, AC-coupled; CLKM AC-grounded (Table 6-6).
    # The oscillator runs off AWR_1V8 (RADAR_EN-gated) so the clock is stable
    # with the rails before reset releases. All-silicon MEMS (robust to launch
    # shock). Kept on the TOP face — NO feature="clock" (which would sweep it to
    # the bottom): the AoP's CLKP is on the top, so the clock sits beside it for
    # the shortest reference route; and as a leadless DFN it's better off the
    # internal bottom face anyway. (The MP25 HSE differs — its OSC balls are on
    # its bottom, so that one keeps feature="clock".)
    osc = add_dsc1001ci5_040_0000(d, ref="Y_AWR_HSE", board_tag=BTAG)
    _net(d, "AWR_1V8")    .connect(osc.pin("1"))   # STANDBY# tied high → run
    _net(d, "GND")        .connect(osc.pin("2"))   # GND
    _net(d, "AWR_OSC_OUT").connect(osc.pin("3"))   # OUT (40 MHz)
    _net(d, "AWR_1V8")    .connect(osc.pin("4"))   # VDD
    cap_to_gnd(d, "AWR_1V8", "100nF", ref="C_AWR_OSC_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG)
    _net(d, "AWR_CLKREF").connect(awr.pin("CLKP"))
    _net(d, "AWR_CLKM")  .connect(awr.pin("CLKM"))
    # External-clock mode per SWRS236 Table 6-6: AC-coupled SINE or
    # DC-COUPLED SQUARE, amplitude 0.7–1.2 V. The DSC1001 is a 1.8 Vpp CMOS
    # square → DC-coupled through a 330/390 divider: 1.8 × 390/720 ≈ 0.98 V
    # square at CLKP (≈2.5 mA oscillator load; ~1.7 ns edge RC against the
    # pin capacitance). The old 100 pF AC-block was the sine-mode coupling
    # at full CMOS swing — wrong on both counts.
    res_between(d, "AWR_OSC_OUT", "AWR_CLKREF", "330",
                ref="R_AWR_CLK_SER", board_tag=BTAG)
    res_between(d, "AWR_CLKREF", "GND", "390",
                ref="R_AWR_CLK_SH", board_tag=BTAG)
    cap_to_gnd(d, "AWR_CLKM", "100pF", ref="C_AWR_CLKM", board_tag=BTAG)  # CLKM AC-gnd (confirm vs TI mmWave HW guide)

    # ── SPI boot flash (SST26WF080B, 8 Mbit/1 MB, SINGLE-bit SPI) ────────────
    # The AWR1843AOP boots its application from this NOR during GROUND staging
    # (depot-BIST sessions re-boot from it; since the Chambered→Ready merge the
    # radar is DARK in Ready and cold-booaxial accelerationsetback) —
    # historically NOT after launch, which was a resume from RAM (power_states.md). So boot
    # latency is ground-side and a plain 4-wire single-SPI bus (CLK/CS/SI/SO) is
    # plenty — no need for the SST26's x2/x4 modes or a 6-wire quad bus. 1 MB >
    # the ~832 KB program-RAM ceiling, so it holds a full image. The image is
    # ENCRYPTED + signed, decrypted in-chip by the AoP HSM (secure boot on the
    # production AWR1843ARBSALPQ1); the MP25 owns/provisions the blob.
    # SST26VF080A (2.7-3.6 V) — the 3.3 V sibling of the original 1.8 V
    # SST26WF080B, swapped when VIOIN moved to 3.3 V: the AWR QSPI bus is
    # VIOIN-domain, so the flash levels must follow. Pin map is 1:1 (pin 7
    # gains a RESET# alternate; tied high = inactive either way).
    # feature="bottom": the saturated top face left no slot for the 6×5 WDFN
    # (packer parked it off-board = the radar overflow). A leadless, low-mass
    # package with its EP soldered down rides the internal bottom face fine,
    # and it drops out of the nose_cap cutout.
    fl = add_sst26vf080a(d, ref="U_AWR_FLASH", feature="bottom", board_tag=BTAG)
    _net(d, "COMP_3V3").connect(fl.pin("VDD"))
    _net(d, "GND")     .connect(fl.pin("VSS"))
    _net(d, "GND")     .connect(fl.pin("EP"))             # exposed pad
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_AWR_FLASH_VCC",
               embedded_cap_absorbs=True, board_tag=BTAG)
    _net(d, "AWR_QSPI_CLK").connect(awr.pin("QSPI_CLK"))
    _net(d, "AWR_QSPI_CLK").connect(fl.pin("SCK"))
    _net(d, "AWR_QSPI_CS") .connect(awr.pin("QSPI_CS_N"))
    _net(d, "AWR_QSPI_CS") .connect(fl.pin("CE#"))
    _net(d, "AWR_QSPI_SI") .connect(awr.pin("QSPI[0]"))    # AWR DQ0 → flash SI
    _net(d, "AWR_QSPI_SI") .connect(fl.pin("SI/SIO0"))
    _net(d, "AWR_QSPI_SO") .connect(awr.pin("QSPI[1]"))    # flash SO → AWR DQ1
    _net(d, "AWR_QSPI_SO") .connect(fl.pin("SO/SIO1"))
    # Single-SPI: tie the quad data lines (SIO2/SIO3) inactive (high).
    _net(d, "COMP_3V3").connect(fl.pin("WP#/SIO2"))               # WP# inactive
    _net(d, "COMP_3V3").connect(fl.pin("RESET#/HOLD#/SIO3"))      # RESET#/HOLD# inactive
    # AWR QSPI[2]/QSPI[3] (quad data) unused in single-SPI mode — left open.

    # ── SOP boot straps → functional / QSPI-flash boot ───────────────────────
    # SOP[2:0] are muxed onto functional balls (datasheet pin table): SOP0=TDO
    # (U10), SOP1=SYNC_OUT (M3), SOP2=PMIC_CLKOUT (V10) — sensed only at power-up.
    # Strapped for QSPI-flash boot; the exact SOP[2:0] decode is TRM-level, so
    # VERIFY against the AWR1843 TRM + the AWR1843AOPEVM jumper defaults.
    _net(d, "AWR_SOP0").connect(awr.pin("TDO"))          # U10
    _net(d, "AWR_SOP1").connect(awr.pin("SYNC_OUT"))     # M3
    _net(d, "AWR_SOP2").connect(awr.pin("PMIC_CLKOUT"))  # V10
    res_between(d, "COMP_3V3", "AWR_SOP0", "10k", ref="R_AWR_SOP0", board_tag=BTAG)  # SOP0=1 (VIOIN domain)
    res_between(d, "AWR_SOP1", "GND",     "10k", ref="R_AWR_SOP1", board_tag=BTAG)  # SOP1=0
    res_between(d, "AWR_SOP2", "GND",     "10k", ref="R_AWR_SOP2", board_tag=BTAG)  # SOP2=0

    # No discrete TX/RX antenna balls (antenna-on-package) and no RGMII path —
    # the radar emits detections over SPIA above.


# Fin-stepper driver count on the fins_module. Each fin gets one DRV8428E
# (HTSSOP-16, integrated FETs), so the four drivers + the G0B1 node MCU +
# the small 5 V boost fit on one Ø34 tile — the retired DRV8711 pre-driver
# (HTSSOP-38 + 8 external FETs each) plus a CAN node once forced a second.
_N_FIN_DRIVERS = 4


def _g0b1_node(d: Design, *, suffix: str, board_tag: str) -> Chip:
    """STM32G0B1 peripheral node MCU on the SYS_SPI bus (MP25 M33 is master),
    with the standard decoupling + reset network. Returns the G0B1 Chip so
    the caller can wire its application GPIO.

    Replaces the former DroneCAN node: the TCAN1042 PHY + the shared CAN
    bus are gone. The node is flashed (G0 SPI system bootloader, AN2606) and
    commanded over SYS_SPI — single-ended over the LGA backbone, no
    transceiver. CS is the per-node `SYS_SPI_CS_<suffix>` line from the MP25 M33."""
    g = add_stm32g0b1rei6n(d, ref=f"U_G0B1_{suffix}", board_tag=board_tag)
    _net(d, "3V3").connect_all(g.pins_by_name("VDD/_VDDA"))
    _net(d, "3V3").connect(g.pin("VDDIO_2"))
    _net(d, "3V3").connect(g.pin("VBAT"))
    # VREF+ — the DAC (PA4 = FIN_VREF, the fin-driver current reference)
    # is active, so VREF+ must sit between 2 V and VDDA (G0B1 DS §power):
    # tie to VDDA (3V3). Floating it leaves the DAC reference undefined.
    # Decap rides the ECM laminate like the other ≤100 nF rail bypasses.
    _net(d, "3V3").connect(g.pin("VREF+"))
    cap_to_gnd(d, "3V3", "100nF", ref=f"C_G0B1_{suffix}_VREF",
               embedded_cap_absorbs=True, board_tag=board_tag)
    _net(d, "GND").connect_all(g.pins_by_name("VSS"))
    _net(d, "GND").connect_all(g.pins_by_name("VSS/_VSSA"))
    cap_to_gnd(d, "3V3", "100nF", ref=f"C_G0B1_{suffix}_VDD1",
               embedded_cap_absorbs=True, board_tag=board_tag)
    cap_to_gnd(d, "3V3", "100nF", ref=f"C_G0B1_{suffix}_VDD2",
               embedded_cap_absorbs=True, board_tag=board_tag)
    cap_to_gnd(d, "3V3", "1uF", ref=f"C_G0B1_{suffix}_BULK",
               board_tag=board_tag)
    nrst = f"G0B1_{suffix}_NRST"
    _net(d, nrst).connect(g.pin("PF2-_NRST"))
    res_between(d, "3V3", nrst, "10k", ref=f"R_G0B1_{suffix}_NRST",
                board_tag=board_tag)
    cap_to_gnd(d, nrst, "100nF", ref=f"C_G0B1_{suffix}_NRST",
               board_tag=board_tag)
    # SYS_SPI slave (SPI3) — shared SCLK/MISO/MOSI from the MP25 M33 root + a
    # per-node chip-select. Carries firmware (ISP) + runtime command/telemetry.
    _net(d, "SYS_SPI_SCLK").connect(g.pin("PC10"))            # SPI3_SCK
    _net(d, "SYS_SPI_MISO").connect(g.pin("PC11"))            # SPI3_MISO
    _net(d, "SYS_SPI_MOSI").connect(g.pin("PC12"))            # SPI3_MOSI
    _net(d, f"SYS_SPI_CS_{suffix}").connect(g.pin("PA15"))    # SPI3_NSS ← MP25 M33
    return g


def _hall_switch(d: Design, *, ref: str, board_tag: str, out_net: str,
                 gpio_chip: Chip, gpio_pin: str) -> None:
    """DRV5023 Hall switch — an OFF-board sensor (it mounts by the moving
    magnet it senses, not on the PCB). The board only lands its three
    wires (VCC / GND / OUT — open-drain digital, no bus) plus the
    required OUT pull-up and local decoupling; the MCU reads OUT as a
    GPIO level."""
    for sig, net in (("VCC", "3V3"), ("GND", "GND"), ("OUT", out_net)):
        pad = add_pogo_pad(d, ref=f"{ref}_{sig}", board_tag=board_tag,
                           manf_pn=None)
        _net(d, net).connect(pad.pin("1"))
    res_between(d, "3V3", out_net, "10k", ref=f"R_{ref}_PU",
                board_tag=board_tag)                    # required pull-up
    cap_to_gnd(d, "3V3", "100nF", ref=f"C_{ref}_VCC", board_tag=board_tag)
    _net(d, out_net).connect(gpio_chip.pin(gpio_pin))


def build_fins_module(d: Design) -> None:
    """Fin actuators — on fin_ble_board (2026-07-30 split: the wakeup tile got
    too crowded, so the fin actuation moved to its own tile; parts carry
    board_tag="fin_ble_board". The WBA55 BLE cluster briefly rode along and
    moved BACK to wakeup_board 2026-07-31 — the wake/activation_unlock ladder rides a
    tile every config carries). The same day's stack reorder (activation
    dropped down between aft_end and cell_floor) made this tile the BATTERY
    COMPARTMENT CEILING — the cells' + contact lands P_CELL_CONTACTS ride
    its bottom face (built in build_power_board) with its embeddable
    passives tucked into the compartment's free trefoil space — and the
    host of the piezo launch cluster (disc + comparator column, top face;
    emitted in build_activation_interface). Both are CORE functions, so
    fin_ble_board is in EVERY config, core_radar included — that config
    still flies RF-dark, shedding only the Yagi leaves. A SYS_SPI
    node (STM32G0B1, MP25 M33 is master) driving the four fin steppers via
    integrated DRV8428E drivers.

    The spin-brake tile was retired (its DRV8833 brake driver dropped as
    redundant); only its FINBOOST boost moved here (now 5 V) — there's room
    because the DRV8428E is tiny (HTSSOP-16, integrated FETs) next to the
    DRV8711 pre-driver it replaces (HTSSOP-38 + 8 external FETs per fin).

    BOM:
      - STM32G0B1REI6N — node MCU (SYS_SPI slave; flashed over SPI ROM
        bootloader by the MP25 M33 root — no CAN transceiver)
      - TPS61175PWPR   — shared 5 V boost on power_board (VMOT taps COMP_5V_RAW)
      - 4× DRV8428EPWPR — integrated bipolar-stepper drivers (one per fin)
      - DRV5023AJQLPG  — Hall position sensor (deploy), OFF-board: 3 wire pads

    DRV8428E is fully integrated: PH/EN control (APH/AEN + BPH/BEN), an
    internal current regulator referenced to VREF (no external sense
    shunts), no SPI and no external FETs. Only the four motor-coil outputs
    leave the tile edge to each fin's stepper.
    """
    BTAG = "fin_ble_board"   # fin actuators on their own tile (2026-07-30 split off wakeup; fins-only since 2026-07-31)
    g = _g0b1_node(d, suffix="FIN", board_tag=BTAG)
    # Shared enable + per-fin PH/EN control lines from the node MCU.
    _net(d, "FIN_NSLEEP").connect(g.pin("PB7"))
    _fin_aen = {1: "PC0", 2: "PC1", 3: "PC2", 4: "PC3"}   # PWM (enable A)
    _fin_aph = {1: "PC4", 2: "PC5", 3: "PC6", 4: "PC7"}   # phase A
    _fin_ben = {1: "PB0", 2: "PB1", 3: "PB2", 4: "PB10"}  # PWM (enable B)
    _fin_bph = {1: "PB3", 2: "PB4", 3: "PB5", 4: "PB6"}   # phase B
    for i in range(1, _N_FIN_DRIVERS + 1):
        _net(d, f"FIN{i}_AEN").connect(g.pin(_fin_aen[i]))
        _net(d, f"FIN{i}_APH").connect(g.pin(_fin_aph[i]))
        _net(d, f"FIN{i}_BEN").connect(g.pin(_fin_ben[i]))
        _net(d, f"FIN{i}_BPH").connect(g.pin(_fin_bph[i]))

    # Shared current-set reference: the node MCU's DAC (DAC_OUT1 = PA4) drives
    # FIN_VREF directly, so firmware sets the fin current globally (run/hold
    # scaling, ramps). VREF inputs are high-Z; a small cap filters the DAC.
    _net(d, "FIN_VREF").connect(g.pin("PA4"))
    cap_to_gnd(d, "FIN_VREF", "100nF", ref="C_FIN_VREF", board_tag=BTAG)

    # ── 4× DRV8428E integrated fin-stepper drivers ───────────────────
    for i in range(1, _N_FIN_DRIVERS + 1):
        drv = add_drv8428epwpr(d, ref=f"U_FIN{i}", board_tag=BTAG)
        _net(d, "COMP_5V_RAW").connect(drv.pin("VM"))
        for gpin in ("PGND", "GND", "EP"):
            _net(d, "GND").connect(drv.pin(gpin))
        _net(d, f"FIN{i}_DVDD").connect(drv.pin("DVDD"))
        cap_to_gnd(d, f"FIN{i}_DVDD", "1uF", ref=f"C_FIN{i}_DVDD",
                   board_tag=BTAG)
        cap_to_gnd(d, "COMP_5V_RAW", "100nF", ref=f"C_FIN{i}_VM", board_tag=BTAG)
        # PH/EN control + shared enable
        _net(d, f"FIN{i}_AEN").connect(drv.pin("AEN"))
        _net(d, f"FIN{i}_APH").connect(drv.pin("APH"))
        _net(d, f"FIN{i}_BEN").connect(drv.pin("BEN"))
        _net(d, f"FIN{i}_BPH").connect(drv.pin("BPH"))
        _net(d, "FIN_NSLEEP").connect(drv.pin("NSLEEP"))
        # Internal current regulator: shared VREF on both bridges; a
        # resistor on DECAY/TOFF sets off-time + smart-tune decay.
        _net(d, "FIN_VREF").connect(drv.pin("VREFA"))
        _net(d, "FIN_VREF").connect(drv.pin("VREFB"))
        _net(d, f"FIN{i}_DECAY").connect(drv.pin("DECAY/TOFF"))
        # 44.2 kΩ ±1% EXACTLY — DECAY/TOFF is a seven-level strap and TI
        # only defines the decode windows for the listed E96 values
        # (level 3 = mixed 30% decay, 16 µs Toff). The previous 47 k sat
        # between the level-3 (≤0.8 V) and level-4 (≥1.0 V) windows.
        res_between(d, f"FIN{i}_DECAY", "GND", "44.2k",
                    ref=f"R_FIN{i}_DECAY", board_tag=BTAG)
        # Motor-coil outputs → off-tile to each fin stepper
        for pn in ("AOUT1", "AOUT2", "BOUT1", "BOUT2"):
            _net(d, f"FIN{i}_{pn}").connect(drv.pin(pn))

    # Local VM bulk — DRV8428 DS pin table: "bypass to PGND with a 0.01 µF
    # ceramic plus a bulk capacitor rated for VM". The per-driver 100 nF
    # covers the local HF bypass; this shared bulk keeps the stepper coil
    # current pulses off the LGA lands (the rail's 22 µF bulk lives on
    # power_board, one gap away). 10 µF → 5×2.2 µF 0603 array.
    cap_to_gnd(d, "COMP_5V_RAW", "10uF", ref="C_FIN_VM_BULK", board_tag=BTAG)

    # Hall position sensor (fin-deploy reference)
    _hall_switch(d, ref="J_HALL_FIN", board_tag=BTAG, out_net="FIN_HALL",
                 gpio_chip=g, gpio_pin="PB13")

    # ── Fin VM rail: merged onto COMP_5V ──────────────────────────────
    # The standalone U_FINBOOST (BAT_PROT->5V) is GONE — the DRV8428E VM now
    # taps COMP_5V_RAW (the shared 5V boost on power_board, 1 gap away). The
    # drivers are gated by FIN_NSLEEP, so the always-on VM is fine. (VMOT_EN /
    # node-MCU PB14 freed.)


def build_aft_end_board(d: Design) -> None:
    """Aft-most service tile (snake start) — the activate board
    (2026-07-31: the sector select + activate chain came here from
    activation; the piezo cluster left for fin_ble_board's top face in the
    same-day stack reorder that also brought activation_interface down to
    be this tile's direct neighbour — see the piezo block). Top face: the
    COMPLETE sector-select chain — the CD74HC4514 4-to-16 decoder, the 16
    DMN6075 select NFETs, the DMP6110 activation_unlock high-side + level shift, HV
    monitor + bleed (see _build_activation_array) — and the EXT_CAN
    gateway (TCAN1042 + terminator) at its TP_CAN pads; all 16
    Y*_ACTIVATE_SEL gate nets are tile-local. Bottom (outer) face: the
    bench-test pogo array + the 16 outbound activate-wire pads + activation_unlock
    common — so every activate net is a top↔bottom via through THIS tile and
    none cross the battery compartment. All emitted by the existing
    builders tagged ``board_tag="aft_end_board"``. In the 3-cell default
    the cells do NOT sit here (they stand on cell_floor_board, past
    activation since the reorder — see build_cell_floor_board); only
    single-cell mode lays its one horizontal cell on this tile (tab lands
    P_CELL_TAB_POS/NEG — the activate bank then shares the top face with the
    cell swath). The boost power stage (ACTIVATE_HV) sits on
    activation_interface — its 2.8 mm inductor doesn't fit this thin
    gap, but since the reorder that is ONE thin gap away, so ACTIVATE_HV no
    longer crosses the battery column. This is the named builder hook
    for the tile; it adds nothing on its own."""
    return


def build_cell_floor_board(d: Design) -> None:
    """The THIN battery-floor tile (between activation_interface and the
    battery spacers since the 2026-07-31 stack reorder) — REINSTATED
    2026-07-30 (same-day revert of a brief deletion: with the cells
    standing on aft_end, the piezo hole + comparator pockets + tab
    chimneys starved the aft LGA joint, 59→20 lands, and moving the
    comparator to the bottom face gave PIEZO_P an unwanted via stub). Now
    6L / ~0.85 mm, NO Cu coin (the potted monolith carries the ~27 g pack's
    setback load — full-stack FEA): it carries the cells' side solder-tab −
    lands (`P_CELL_TAB_NEG1..3`, inside the cell bore circles, GND; built in
    build_power_board), the backbone LGA/filled-via pass-through, and TWO
    potting pass-through holes so the thin aft gaps below it
    (activation↔cell_floor, and via activation's own holes
    aft_end↔activation) fill from the compartment channels. The
    compartment sits nose-ward of this tile, up to the fin_ble_board
    ceiling. Dropped in single-cell mode. This is the named builder hook
    for the tile; it adds nothing on its own."""
    return


def build_activation_interface(d: Design) -> None:
    """Aft electronics: the 46-pad grouped bench-bringup pogo array + (since
    2026-07-31) the sector select + activate chain and the EXT-CAN gateway
    — all tagged ``board_tag="aft_end_board"`` and physically mounting on
    the aft_end_board tile; the piezo launch detector is emitted here too
    but rides fin_ble_board's top face (see the piezo block).
    activation_interface itself moved DOWN in the 2026-07-31 stack
    reorder — it now sits between aft_end_board and cell_floor_board, so
    its ACTIVATE_HV boost power stage (top face, 2.8 mm inductor) feeds the
    aft_end activate bank across ONE thin gap instead of the battery column.
    Its battery-connector role went with the compartment: the cell +
    contact pads (P_CELL_CONTACTS, built in build_power_board) now ride
    fin_ble_board's bottom face, the compartment ceiling. This tile's
    bottom face stays chip-free (lands only — a bottom-face part sees
    setback as joint TENSION, see the piezo block); its top also hosts
    the H3LIS331 high-g accel (near the spin axis; built in
    build_wakeup_board with board_tag="activation_interface"). The AON
    latch moved to wakeup_board and the activate chain + CAN gateway to
    aft_end_board in the 2026-07-31 redistribution/swap. The function
    name is kept (many sims/tools enumerate it). Each pogo pad is a
    single-net landing for an external fixture (oscilloscope, current
    shunt, BOOT0 jumper, ISP programmer, etc.).

    The array exposes each MCU's purpose pins plus the system serial buses:
    programming (SWD + BOOT0/NRST to the MP25 M33), the SYS_SPI ISP bus and
    SYS_I2C control/sensor bus (the CAN replacement), the live fin-driver
    lines, spare GPIO, and power. The retired CAN + spin-brake pads are gone."""
    # Bottom-face bench pad map (2026-09-10 re-layout). Grouped by function
    # in rows around the centred activation_unlock common, at the array's 2.101 mm
    # pitch; positions are pinned in locked_placements.json so the silkscreen
    # groups and the bench fixture stay in step. The four TP_ACT_MOTOR*
    # single-phase probes are GONE — every fin now surfaces its FULL bipolar
    # pair set (A1/A2 + B1/B2), so a stepper can actually be driven from this
    # face rather than only probed.
    POGOS = {
        # ── SPI ── SYS_SPI ISP root (MP25 SPI2 -> G0B1 SPI3 slaves)
        "TP_SPI_MOSI":    "SYS_SPI_MOSI",
        "TP_SPI_CS_FIN":  "SYS_SPI_CS_FIN",
        "TP_SPI_MISO":    "SYS_SPI_MISO",
        "TP_SPI_SCLK":    "SYS_SPI_SCLK",
        # ── FIN 1..4 ── full bipolar coil pairs, one row per fin pair.
        # Each coil's two lands are ADJACENT so the go/return currents
        # cancel: these are PWM-switched phases crossing 22 LGA lands to
        # reach the drivers on fin_ble_board, and pair adjacency is what
        # keeps the loop area (and the stack-length radiator) small.
        "TP_FIN1_A1":     "FIN1_AOUT1",
        "TP_FIN1_A2":     "FIN1_AOUT2",
        "TP_FIN1_B1":     "FIN1_BOUT1",
        "TP_FIN1_B2":     "FIN1_BOUT2",
        "TP_FIN2_A1":     "FIN2_AOUT1",
        "TP_FIN2_A2":     "FIN2_AOUT2",
        "TP_FIN2_B1":     "FIN2_BOUT1",
        "TP_FIN2_B2":     "FIN2_BOUT2",
        "TP_FIN3_A1":     "FIN3_AOUT1",
        "TP_FIN3_A2":     "FIN3_AOUT2",
        "TP_FIN3_B1":     "FIN3_BOUT1",
        "TP_FIN3_B2":     "FIN3_BOUT2",
        "TP_FIN4_A1":     "FIN4_AOUT1",
        "TP_FIN4_A2":     "FIN4_AOUT2",
        "TP_FIN4_B1":     "FIN4_BOUT1",
        "TP_FIN4_B2":     "FIN4_BOUT2",
        # NOTE: no TP_FIN_VREF. The shared DRV8428E current-set reference is
        # NOT surfaced on this face (omitted from the final pad map) — there
        # is no bench access to the fin current setpoint. FIN_VREF still
        # crosses the joints; only the aft pad is gone.
        # ── CAN ── client-extension gateway (MP25 FDCAN1 -> TCAN1042)
        "TP_CAN_N":       "EXT_CAN_N",
        "TP_CAN_P":       "EXT_CAN_P",
        # ── BAT ── power monitor / shunt insertion
        "TP_BAT_RAW":     "BAT_RAW",
        "TP_BAT_PROT":    "BAT_PROT",
        # ── activation_unlock ── activate-rail unlock command + monitor. TP_ACT_SET drives the
        # activate-rail high side: driving it on a bench makes Zone A live.
        "TP_ACT_CONFIRM": "ACTIVATE_CONFIRM",
        "TP_ACT_SET":     "ACTIVATE_SET",
        # ── GROUND ── the single bench ground
        "TP_GND_ACT":     "FLEX_GND",
        # ── HALL ── fin-deploy DRV5023 (OFF-board). HALL_VIN exposes the
        # sensor's own 3V3 rail -- NOT the 3V3_AON that TP_VDD carries --
        # so the open-drain OUT reads meaningfully only when 3V3 is up.
        "TP_FIN_HALL":    "FIN_HALL",
        "TP_HALL_VIN":    "3V3",
        # ── I2C ── SYS_I2C control / sensor / payload bus
        "TP_I2C_SDA":     "SYS_I2C_SDA",
        "TP_I2C_SCL":     "SYS_I2C_SCL",
        # ── PROGRAM_MP25 ── Tag-Connect TC2030-CTX signal ORDER so a stock
        # 6-pad Cortex fixture maps straight onto it, then the straps.
        # BOOT0 sits LAST and adjacent to GND, never next to VDD: it has a
        # 10 k pull-down, so a bridge to ground is a no-op while a bridge to
        # the rail would silently drop the MP25 into the ROM bootloader.
        "TP_VDD":         "3V3_AON",
        "TP_SWDIO":       "COMP_SWDIO",
        "TP_NRST":        "NRST",
        "TP_SWCLK":       "COMP_SWDCLK",
        "TP_MP25_GND1":   "FLEX_GND",
        "TP_SWO":         "SWO",
        "TP_MP25_GND2":   "FLEX_GND",
        "TP_BOOT0":       "BOOT0",
        # ── GPIO ── 4-to-16 sector-decoder address lines (NOT spares while
        # the activate rail has activation_unlock -- they select which sector activates)
        "TP_GPIO_0":      "GPIO_EXT_0",
        "TP_GPIO_1":      "GPIO_EXT_1",
        "TP_GPIO_2":      "GPIO_EXT_2",
        "TP_GPIO_3":      "GPIO_EXT_3",
    }
    # Pin-1 convention: the FIRST pad of each silkscreen group is SQUARE,
    # the rest round. Same 2.0 mm size and pitch either way — the silhouette
    # alone tells a bench user where a group starts, with no legend to read.
    # Single-pad groups (activate, GROUND) get no marker: there is no run to start.
    SQUARE_STARTS = {
        "TP_SPI_MOSI",                                     # SPI
        "TP_FIN1_A1", "TP_FIN2_A1", "TP_FIN3_A1", "TP_FIN4_A1",   # FIN 1..4
        "TP_CAN_N",                                        # CAN
        "TP_BAT_RAW",                                      # BAT
        "TP_ACT_CONFIRM",                                  # activation_unlock
        "TP_FIN_HALL",                                     # HALL
        "TP_I2C_SDA",                                      # I2C
        "TP_JUMP_WAKE",                                    # JUMPSTART
        "TP_VDD",                                          # PROGRAM_MP25
        "TP_GPIO_0",                                       # GPIO
    }
    for ref, net in POGOS.items():
        # Pogo pads have no MFG PN; system.py treats them as bare PCB
        # geometry. Smash factory defaults to manf_pn="Pogo_Pad_D2.0mm"
        # (the part's internal designation) — override to match.
        pad = add_pogo_pad(d, ref=ref, board_tag="aft_end_board",
                           manf_pn=None, square=ref in SQUARE_STARTS)
        _net(d, net).connect(pad.pin("1"))

    # ── piezo launch/impact sensor — fin_ble top, compression-loaded ──
    # Steminc SMD10T04R111 bare PZT disc (Ø10 × 0.4 mm, SM111 hard PZT,
    # wrap-around electrode) reflowed flat onto fin_ble_board's TOP face on
    # the spin axis (2026-07-31 stack reorder, user call: the disc + column
    # swapped off the saturated aft_end top; fin_ble — now the battery
    # compartment ceiling — has the room). The TOP (nose-facing) face is
    # the hard rule (user-confirmed over the compartment-side bottom):
    #   • MECHANICAL — setback throws every part AFT, so a nose-facing
    #     (top) face loads the disc in COMPRESSION against rigid FR4
    #     (~1-2 MPa vs >500 MPa PZT compressive strength; this is also the
    #     bonded-compression sensing mode). An aft-facing mount inverts
    #     that: the disc's ~0.25 g is ~114 N at 46.7 kG carried by the
    #     In52 joints in TENSION (~10-14 MPa ≈ the alloy's UTS), or by the
    #     potting pillar behind it — where any fill void becomes a bending
    #     span, and PZT in bending (~80-100 MPa, less at solder stress
    #     risers) cracks. Never mount the ceramic on an aft-facing face.
    #   • THERMAL — PZT depoles above ~Curie/2 ≈ 160 °C, so the disc can
    #     only be attached in the final In52/Sn48 118 °C step. ⚠ OPEN
    #     ASSEMBLY ITEM: the disc's face now sits in the fin_ble↔wakeup
    #     gap, so the fold/pot sequence must keep that gap open (attach the
    #     disc, close the fold, pot) — verify against the assembly order.
    # It replaced the CEB-21018-L100 brass diaphragm (−20…+60 °C — the
    # narrowest-rated part in the round; SM111's ~320 °C Curie clears the
    # full envelope) and with it the milled pocket: a rigid bonded disc
    # needs no recess or flex gap. Bonded-compression sensing scales with
    # thickness² (diameter-independent): ~5–7 V at 20 kG vs the 0.30 V
    # threshold. Two pads: MAIN electrode → sense node, WRAP (top electrode
    # brought around) → GND.
    #
    # A LOCAL TLV3691 thresholds PIEZO_P → COMP_OUT (= piezo_over_threshold),
    # which crosses to the M33 PD5 EXTI for a near-instant launch interrupt.
    # The comparator + its resistors ride the SAME top face right beside the
    # disc (the EE's hand-placed x≈8.5 column) so the high-impedance PIEZO_P
    # charge node stays microscopically short — only the digital edge
    # crosses off-tile (and the hub is now 2 gaps away, not 5). The packer
    # fits the fins cluster (G0B1 + 4× DRV8428E) around these locks.
    # ACTIVATE_SET / ACTIVATE_CONFIRM are firmware GPIOs now — the old hardware
    # confirm AND-gate is gone. The comparator runs off the always-on bootstrap
    # 3V3 (exposed on the aft_end TP_VDD pogo) so the detector is alive while
    # the unit waits for launch. Complements the H3LIS331 high-G accel (on
    # activation_interface): the H3LIS gives the quantitative ±400 g over
    # I²C, the piezo the fast edge.
    piezo = add_piezo_disc_smd10t04r111(d, ref="P_PIEZO",
                                        board_tag="fin_ble_board")
    _net(d, "PIEZO_P").connect(piezo.pin("1"))   # MAIN (bottom electrode)
    _net(d, "GND")    .connect(piezo.pin("2"))   # WRAP (top electrode, wrapped)
    res_between(d, "PIEZO_P", "GND", "1M", ref="R_PIEZO_BLEED",
                board_tag="fin_ble_board")   # DC return + charge bleed
    res_between(d, "PIEZO_P",  "COMP_INP", "100k", ref="R_COMP_SER",
                board_tag="fin_ble_board")
    res_between(d, "3V3_AON",  "COMP_INM", "1M",   ref="R_THR1",
                board_tag="fin_ble_board")
    res_between(d, "COMP_INM", "GND",      "100k", ref="R_THR2",
                board_tag="fin_ble_board")
    # TLV3691 nanopower comparator (~0.15 µA Iq) — replaces the LMV331 so the
    # launch detector can stay on the always-on 3V3 without being an ~80 µA shelf
    # load. Push-pull output → NO pull-up (the LMV331's R_COMP_PU is gone, which
    # would otherwise sink ~33 µA whenever COMP_OUT is low ≈ always). V+ is pin 6
    # (pin 5 is NC). COMP_OUT drives the M33 PD5 EXTI directly.
    comp = add_tlv3691idpfr(d, ref="U_COMP_PZ", board_tag="fin_ble_board")
    _net(d, "COMP_INP").connect(comp.pin("1"))   # IN+
    _net(d, "GND")     .connect(comp.pin("2"))   # GND / V−
    _net(d, "COMP_INM").connect(comp.pin("3"))   # IN−
    _net(d, "COMP_OUT").connect(comp.pin("4"))   # OUT (push-pull) → M33 PD5 EXTI
    # pin 5 = NC (no connect)
    _net(d, "3V3_AON") .connect(comp.pin("6"))   # VCC (launch detector active from Standby on)
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_COMP_PZ",
               board_tag="fin_ble_board")   # local comparator decoupling

    _build_activation_array(d)


# ── aft activation array — 12-sector capacitive-discharge activate ──
def _build_activation_array(d: Design) -> None:
    """12 circular outbound activate-wire sectors, current-source activated (no cap).

    A TPS61175 boost makes ACTIVATE_HV = 33 V (off COMP_5V) and sources the
    activate current DIRECTLY — no reservoir cap. At this operating point one
    sector is ~30 mm of 25 µm / fine outbound at current density
    ~1000 A/mm²: V = J·ρ·L = 33 V, the wire draws ~20-120 mA depending on
    gauge (0.65-4 W), and self-fuses adiabatically in ~5 ms. That power is
    well within the boost's ~280 mA @ 33 V output, so the old activate cap
    (and the cell-pulse problem it solved) is GONE — the wire is the load.

    Selection:  GPIO_EXT_0..3 → CD74HC4514 4-to-16 decoder (powered from
                BAT_PROT so it is dead in shelf/standby AND its ~4 V outputs
                fully drive the DMN6075 gates while the 3.3 V GPIO inputs
                stay valid HC highs; a 5 V VCC would fail V_IH). E tied low
                (always decoding), LE tied high (transparent). Y0..Y15 → 16
                low-side DMN6075 select NFETs (full 16-sector array).
    Unlock/activate: ACTIVATE_SET → DMP6110 high-side activation_unlock (ACTIVATE_HV → the sector
                commons). Without activation_unlock, ACTIVATE_HV can't reach any wire even if a
                select NFET shorts. The PFET gate is a resistor divider
                (R1=R2=100k off ACTIVATE_HV) → V_GS ≈ -16.5 V at 33 V, inside
                the ±20 V limit (no zener).
    Monitor:    ACTIVATE_HV → 100k/11k divider → ACTIVATE_CONFIRM (MP25 ADC) so
                firmware verifies the 33 V rail before activate; R_ACTIVATE_BLEED
                discharges the small output cap when activation_unlock is released.

    Both 33 V (vs the cap's 25 V) and 60 V FETs are comfortable; only the
    boost's mandatory output ceramic remains on ACTIVATE_HV (50 V, loop
    stability — NOT an activate reservoir). All on aft_end_board. SAFETY
    (eFuse-gated decoder + activation_unlock interlock): no wire activates unless the round
    is in MAIN (BAT_PROT live) AND ACTIVATE_SET sets activation_unlock on the high side."""
    # SECTOR SELECT + ACTIVATE CHAIN on aft_end_board's TOP face (moved here
    # from activation 2026-07-31; the piezo cluster moved OUT to
    # fin_ble_board's top in the same-day stack reorder, freeing the room
    # that lets the whole chain sit together): the CD74HC4514 4-to-16
    # decoder, 16 select NFETs, activation_unlock high-side + level shift, HV monitor and
    # bleed all sit ONE via away from the outbound wire-pad ring + common
    # on aft_end's bottom face — the 16 Y*_ACTIVATE_SEL gate nets are
    # tile-local, and ACT_WIRE_0..15 + activation_unlock never cross the battery
    # compartment. ACTIVATE_HV comes down from the boost on activation, which
    # the reorder made the DIRECT neighbour (one thin gap, not the battery
    # column; the 2.8 mm inductor still doesn't fit this tile's thin gap).
    # The bench pogos + wire pads + common ride aft_end's BOTTOM (aft
    # service) face.
    BT = "aft_end_board"
    # ── activate-rail boost: COMP_5V → ACTIVATE_HV 33 V (TPS61175) ──────────────
    # Fed from COMP_5V (not BAT_PROT): 5→33 V is 85 % duty vs 88 % from a
    # depleted cell — comfortable headroom under the TPS61175 ~89 % DMAX.
    # The boost POWER STAGE lives one tile up on ACTIVATION_INTERFACE
    # (top face): its 2.8 mm WE-PD inductor would force the thin
    # aft_end↔activation spacer to grow by ~1 mm, and in single-cell mode
    # aft_end's top also hosts the horizontal cell swath (|x| < 7.55 mm),
    # which the boost's three big bodies don't fit around. Since the
    # 2026-07-31 stack reorder activation is aft_end's DIRECT neighbour,
    # so ACTIVATE_HV (unswitched) crosses only that one thin gap — no longer
    # the battery column (its feed COMP_5V now rides the column lands down
    # from power_board instead; 33 V across 0.37 mm potted land gaps was
    # fine per IPC-2221, and the 5 V rail is more comfortable still); the
    # activation_unlock high-side, decoder, NFETs, monitor and bleed sit on aft_end with
    # the wires — safety topology unchanged.
    BT_BOOST = "activation_interface"
    boost = add_tps61175pwpr(d, ref="U_ACTIVATE_BOOST", board_tag=BT_BOOST)
    _net(d, "COMP_5V")    .connect(boost.pin("VIN"))     # 3
    _net(d, "ACTIVATE_SW")    .connect(boost.pin("SW_1"))    # 1
    _net(d, "ACTIVATE_SW")    .connect(boost.pin("SW_2"))    # 2
    _net(d, "ACTIVATE_FB")    .connect(boost.pin("FB"))      # 9
    for p in ("PGND_1", "PGND_2", "PGND_3", "AGND", "EP", "NC", "SYNC"):
        _net(d, "GND")    .connect(boost.pin(p))
    # EN = COMP_5V: ACTIVATE_HV is live whenever the round is in MAIN. The activation_unlock
    # interlock + bleed keep it safe until ACTIVATE_SET activates.
    _net(d, "COMP_5V")    .connect(boost.pin("EN"))      # 4
    _net(d, "ACTIVATE_COMP")  .connect(boost.pin("COMP"))    # 8
    _net(d, "ACTIVATE_FREQ")  .connect(boost.pin("FREQ"))    # 10
    res_between(d, "ACTIVATE_FREQ", "GND", "176k", ref="R_ACTIVATE_FREQ", board_tag=BT_BOOST)  # 600 kHz
    _net(d, "ACTIVATE_SS")    .connect(boost.pin("SS"))      # 5
    cap_to_gnd(d, "ACTIVATE_SS", "47nF", ref="C_ACTIVATE_SS", board_tag=BT_BOOST)
    cap_to_gnd(d, "COMP_5V", "10uF", ref="C_ACTIVATE_IN", board_tag=BT_BOOST)
    # WE-PD 10 µH (DS 4.7-47 µH window) — reused from the COMP_5V boost.
    # D_ACTIVATE keeps the MBRS540T3G: the 33 V output leaves only 7 V of V_RRM
    # margin, so this rectifier is NOT a candidate for the 40 V flat part
    # until that headroom is revisited (it is now the only MBRS540 user).
    l_activate = add_we_744043100(d, ref="L_ACTIVATE", board_tag=BT_BOOST)
    _net(d, "COMP_5V").connect(l_activate.pin("1"))
    _net(d, "ACTIVATE_SW") .connect(l_activate.pin("2"))
    d_activate = add_mbrs540t3g(d, ref="D_ACTIVATE", board_tag=BT_BOOST)
    _net(d, "ACTIVATE_SW").connect(d_activate.pin("A"))
    _net(d, "ACTIVATE_HV").connect(d_activate.pin("K"))
    # FB: VOUT = 1.229 × (1 + 261/10) = 33.3 V
    res_between(d, "ACTIVATE_HV", "ACTIVATE_FB", "261k", ref="R_ACTIVATE_FB1", board_tag=BT_BOOST)
    res_between(d, "ACTIVATE_FB", "GND",     "10k",  ref="R_ACTIVATE_FB2", board_tag=BT_BOOST)
    # COMP RC — light load (the wire), loop non-critical; reuse known values.
    res_between(d, "ACTIVATE_COMP", "ACTIVATE_COMP_C", "1.6k", ref="R_ACTIVATE_COMP", board_tag=BT_BOOST)
    cap_to_gnd(d, "ACTIVATE_COMP_C", "220nF", ref="C_ACTIVATE_COMP", board_tag=BT_BOOST)
    # Boost output ceramic — loop stability only (DS wants ≥4.7 µF out), NOT
    # an activate reservoir. cap_to_gnd dispatches 4.7 µF → 50 V KEMET 0603.
    cap_to_gnd(d, "ACTIVATE_HV", "4.7uF", ref="C_ACTIVATE_OUT", board_tag=BT_BOOST)

    # ── bleed + HV monitor ─────────────────────────────────────────────
    res_between(d, "ACTIVATE_HV", "GND", "100k", ref="R_ACTIVATE_BLEED", board_tag=BT)
    # HV monitor: 33 V × 11/(100+11) = 3.27 V into the MP25 ADC.
    res_between(d, "ACTIVATE_HV", "ACTIVATE_CONFIRM", "100k",
                ref="R_ACTIVATE_MON1", board_tag=BT)
    res_between(d, "ACTIVATE_CONFIRM", "GND", "11k",
                ref="R_ACTIVATE_MON2", board_tag=BT)

    # ── high-side activation_unlock (DMP6110) + level-shift + gate-clamp divider ─────
    unlock = add_dmp6110svt_7(d, ref="Q_ACTIVATION_UNLOCK", board_tag=BT)
    for dp in ("D_1", "D_2", "D_3", "D_4"):
        _net(d, "ACTIVATION_UNLOCK").connect(unlock.pin(dp))   # drains → sector common
    _net(d, "ACTIVATE_HV")   .connect(unlock.pin("S"))      # source = the 33 V rail
    _net(d, "ACTIVATION_UNLOCK_G").connect(unlock.pin("G"))
    # gate divider: ACTIVATE_HV ─100k─ G ─100k─ (BSS138 drain). activation_unlock → G≈16.5 V
    # → V_GS≈-16.5 V (PFET on, inside ±20 V); without activation_unlock → G=ACTIVATE_HV (off).
    res_between(d, "ACTIVATE_HV", "ACTIVATION_UNLOCK_G", "100k", ref="R_ACTIVATION_UNLOCK_H", board_tag=BT)
    res_between(d, "ACTIVATION_UNLOCK_G", "ACTIVATION_UNLOCK_GD", "100k", ref="R_ACTIVATION_UNLOCK_L", board_tag=BT)
    q_unlock = add_bss138lt1g(d, ref="Q_ACTIVATION_UNLOCK_LS", board_tag=BT)
    _net(d, "ACTIVATION_UNLOCK_GD").connect(q_unlock.pin("3"))   # drain
    _net(d, "GND")        .connect(q_unlock.pin("2"))   # source
    _net(d, "ACTIVATE_SET").connect(q_unlock.pin("1"))  # gate ← MP25 activation_unlock

    # ── 4-to-16 sector decoder (CD74HC4514PW, BAT_PROT-powered) ───────
    # Back on aft_end's TOP face with the select NFETs it drives (a brief
    # 2026-07-31 hop to fin_ble_board was superseded the same day by the
    # stack reorder: the piezo cluster left for fin_ble instead, freeing
    # this face) — the 16 Y*_ACTIVATE_SEL gate nets are tile-local, and its
    # A0..A3 / BAT_PROT inputs already terminate at aft_end bench pogos.
    dec = add_cd74hc4514pw(d, ref="U_ACTIVATE_DEC", board_tag=BT)  # TSSOP-24, aft_end top
    _net(d, "BAT_PROT").connect(dec.pin("VCC"))
    _net(d, "GND")     .connect(dec.pin("GND"))
    _net(d, "GPIO_EXT_0").connect(dec.pin("A0"))
    _net(d, "GPIO_EXT_1").connect(dec.pin("A1"))
    _net(d, "GPIO_EXT_2").connect(dec.pin("A2"))
    _net(d, "GPIO_EXT_3").connect(dec.pin("A3"))
    _net(d, "GND")     .connect(dec.pin("~{E}"))     # active-low enable → always decoding
    _net(d, "BAT_PROT").connect(dec.pin("~{LE}"))    # active-high latch → transparent

    # ── 16 low-side select NFETs + outbound activate-wire pads ─────────────
    # ALL 16 decoder outputs Y0..Y15 are used → a full 16-sector radial array
    # (30°→22.5° per sector.
    # Each sector: activation_unlock (common) → outbound wire → ACT_WIRE_i pad →
    # DMN6075 drain; source → GND. Only the addressed sector's gate is high,
    # and only activation_unlock ACTIVATE_HV makes current flow → exactly one wire activates.
    # NB: no spare Y12..Y15 "no-sector" idle code anymore — the safe idle state is
    # the DMP6110 activation_unlock (ACTIVATE_HV gated off); tie ~E to a GPIO if a hard all-off
    # decoder state is also wanted.
    # Activate-wire pads on aft_end_board's BOTTOM face (the aft outbound activation
    # interface) — the outbound wires attach at the outbound activation. With the NFETs +
    # activation_unlock back on aft_end's top face (2026-07-31), ACT_WIRE_i (drain → pad)
    # and activation_unlock (high-side → common) are plain top↔bottom vias through this
    # one tile — nothing activate-side crosses the battery compartment. Pads laid
    # out as a ring of 16 around the rim (one per sector) via
    # locked_placements; common centred.
    common = add_pogo_pad(d, ref="P_ACTIVATE_COMMON", board_tag="aft_end_board", manf_pn=None, feature="bottom")
    _net(d, "ACTIVATION_UNLOCK").connect(common.pin("1"))
    for i in range(16):
        nfet = add_dmn6075sq_7(d, ref=f"Q_ACTIVATE_N{i}", board_tag=BT)
        _net(d, f"Y{i}_ACTIVATE_SEL").connect(nfet.pin("G"))
        _net(d, f"ACT_WIRE_{i}") .connect(nfet.pin("D"))
        _net(d, "GND")           .connect(nfet.pin("S"))
        _net(d, f"Y{i}_ACTIVATE_SEL").connect(dec.pin(f"Y{i}"))
        # Sector 0 is SQUARE — the ring's start marker, so the 16 outbound
        # lands can be counted round from a known origin during harnessing.
        pad = add_pogo_pad(d, ref=f"P_ACT_WIRE_{i}", board_tag="aft_end_board",
                           manf_pn=None, feature="bottom", square=(i == 0))
        _net(d, f"ACT_WIRE_{i}").connect(pad.pin("1"))


def build_camera_module(d: Design) -> None:
    """AR0234CS 2.3-MP monochrome global-shutter image sensor (83-ball
    ODCSP) + power-rail decoupling caps + RSVD pulldown. 2-lane MIPI
    CSI-2 + I²C + EXTCLK + RESET_BAR control. All on a small Ø15 mm
    tile behind the 1064 nm bandpass lens — see system.py:add_camera
    for the design rationale."""
    cam = add_ar0234cssm00suka0_cp(d, ref="U_CAM", board_tag="camera_module")

    # ── Power rails (per datasheet Table 3) ─────────────────────────
    # 1.2V (VDD, VDD_PHY, VDD_DATA): PMIC-supplied
    for ball in ["A4", "A8", "A12", "B10", "D7", "E1", "G8"]:
        _net(d, "COMP_1V2", kind="power", voltage_v=1.2).connect(cam.pin(ball))
    _net(d, "COMP_1V2").connect(cam.pin("C8"))       # VDD_PHY
    _net(d, "COMP_1V2").connect(cam.pin("F11"))      # VDD_DATA

    # 1.8V (VDD_IO, VDDIO_PHY): logic level for MP25 SDIO/CSI
    for ball in ["A7", "B4", "B5", "B11", "D3", "D6", "F1", "G12"]:
        _net(d, "COMP_1V8", kind="power", voltage_v=1.8).connect(cam.pin(ball))
    _net(d, "COMP_1V8").connect(cam.pin("D10"))      # VDDIO_PHY

    # 2.8V (VAA, VAA_PIX, VAA_PHY): analog supply for image sensor
    for ball in ["A10", "B1", "G2", "G7"]:
        _net(d, "COMP_2V8", kind="power", voltage_v=2.8).connect(cam.pin(ball))  # VAA
    for ball in ["B8", "C2", "G1", "G9"]:
        _net(d, "COMP_2V8").connect(cam.pin(ball))   # VAA_PIX
    _net(d, "COMP_2V8").connect(cam.pin("F8"))       # VAA_PHY

    # ── Grounds ─────────────────────────────────────────────────────
    for ball in ["A2", "A3", "A6", "B2", "C1", "C5", "D8", "D9",
                 "E2", "E8", "F2", "F9", "G10"]:
        _net(d, "GND", kind="ground").connect(cam.pin(ball))    # DGND
    for ball in ["A9", "C3", "G3", "G6"]:
        _net(d, "GND").connect(cam.pin(ball))                   # AGND
    for ball in ["B12", "E7"]:
        _net(d, "GND").connect(cam.pin(ball))                   # GNDIO_PHY

    # ── MIPI CSI-2 (2-lane: D0+D1 used; D2+D3 NC) ──────────────────
    _net(d, "CAM_CSI_D0_P") .connect(cam.pin("C9"))
    _net(d, "CAM_CSI_D0_N") .connect(cam.pin("C10"))
    _net(d, "CAM_CSI_D1_P") .connect(cam.pin("C12"))
    _net(d, "CAM_CSI_D1_N") .connect(cam.pin("C11"))
    _net(d, "CAM_CSI_CLK_P").connect(cam.pin("D11"))
    _net(d, "CAM_CSI_CLK_N").connect(cam.pin("D12"))

    # ── I²C + control ───────────────────────────────────────────────
    _net(d, "CAM_SCL")   .connect(cam.pin("F6"))     # SCLK
    _net(d, "CAM_SDA")   .connect(cam.pin("E6"))     # SDATA
    _net(d, "CAM_NRST")  .connect(cam.pin("F7"))     # RESET_BAR
    _net(d, "CAM_EXTCLK").connect(cam.pin("G11"))    # 27 MHz from MP25

    # ── Strap pins to GND (defaults per datasheet) ──────────────────
    _net(d, "GND").connect(cam.pin("A5"))   # SADDR — I²C addr 0x20/0x21
    _net(d, "GND").connect(cam.pin("B6"))   # OE_BAR — MIPI mode
    _net(d, "GND").connect(cam.pin("F5"))   # TEST — normal operation
    _net(d, "GND").connect(cam.pin("D5"))   # TRIGGER — not used

    # ── Required passives per datasheet ─────────────────────────────
    # RSVD (F10): 1.5kΩ to DGND. res_between needs net names — use
    # an explicit named net (system.py emits the anon N$XX, but the
    # alias mechanism will resolve the merge if we add an explicit
    # name on either side).
    _net(d, "CAM_RSVD").connect(cam.pin("F10"))
    res_between(d, "CAM_RSVD", "GND", "1.5k", ref="R_CAM_RSVD",
                board_tag="camera_module")

    # CAP_1UF_PHY (F12): 1 µF decoupling for MIPI regulator
    _net(d, "CAM_PHY_REG").connect(cam.pin("F12"))
    cap_to_gnd(d, "CAM_PHY_REG", "1uF", ref="C_CAM_PHY_REG",
               board_tag="camera_module")

    # ── Power-rail decoupling ───────────────────────────────────────
    # 100 nF HF caps absorbed by the ECM laminate; 1 µF bulk stays
    # discrete for frame-rate current swings.
    cap_to_gnd(d, "COMP_1V2", "100nF", ref="C_CAM_VDD_1",
               embedded_cap_absorbs=True, board_tag="camera_module")
    cap_to_gnd(d, "COMP_1V2", "1uF",   ref="C_CAM_VDD_BULK",
               board_tag="camera_module")
    cap_to_gnd(d, "COMP_1V8", "100nF", ref="C_CAM_VDDIO_1",
               embedded_cap_absorbs=True, board_tag="camera_module")
    cap_to_gnd(d, "COMP_1V8", "1uF",   ref="C_CAM_VDDIO_BULK",
               board_tag="camera_module")
    cap_to_gnd(d, "COMP_2V8", "100nF", ref="C_CAM_VAA_1",
               embedded_cap_absorbs=True, board_tag="camera_module")
    cap_to_gnd(d, "COMP_2V8", "1uF",   ref="C_CAM_VAA_BULK",
               board_tag="camera_module")


def build_nose_cap(d: Design) -> None:
    """Terminal forward-end tile (radar builds only): the **nose cap** — a thin
    (~0.6 mm) Ø34 disc that closes the projectile nose. It (1) carries the depot
    **USB-C** on its outer, post-potting-accessible face, (2) carries the
    **IR service-link window** (the RX/TX pair lives on the radar face under
    its through-cuts), and (3) structurally **supports the aluminium waveguide
    disk** so the disk's setback load runs nose_cap → body, NOT through the AWR.

    Stack (radar tile top = ref, +Z toward the nose): the AWR2E44P (1.234 mm
    tall) sits on the radar; the radar↔nose_cap spacer is sized to
    `AWR_height − nose_cap_thickness` so the nose_cap's OUTER face lands flush
    with the AWR top. The waveguide disk sits just beyond, across an **air gap**
    (choke-flange transition). That gap MUST stay air: Smash's black Stycast
    2651MM is a ~0.8 dB/mm absorber at 77 GHz, so the **potting line stops at the
    AWR top** and never fills the coupling gap (see ref_stycast_mmwave_loss).

    USB-C is the depot service port — **power-in** (VBUS → BAT_PROT via the 5 A OR
    Schottky on power_board, so the TPS25940 eFuse's reverse-blocking keeps the
    primary cells isolated while USB runs the whole unit) **+ USB2 data** (D± →
    MP25 USB-FS for SSH / USB-DFU). The connector is a Same Sky UJ20 — a 16-pin
    USB2-only IP67 receptacle SMT-mounted on the cap's OUTER face (the cap is now
    1.455 mm — too thick for the UJ20's ~1 mm mid-mount slot, so it surface-mounts;
    SBU contacts unconnected)."""
    BTAG = "nose_cap"
    _net(d, "GND", kind="ground")

    # ── Depot USB-C (UJ20 USB2 IP67, SMT on the RADAR top face) ─────────────
    # Lowered from the nose_cap onto the radar's nose-facing top face at the SAME
    # (0,12) north-rim spot (nothing else sits there): it pokes UP through a
    # clearance cavity retained in the nose_cap (_mark_usb_cavity) instead of
    # sitting on the nose_cap's OUTER face, so its body no longer protrudes past
    # the nose tip — reclaims its height from the stack. The 17 mm N chord moves
    # to the radar with it (kicad_pcb.py). board_tag=radar_module; the lock keeps
    # (0,12)/face=top (radar→nose is an identity fold, so top still faces the nose).
    # 16-contact USB2 receptacle; the pads combine the A/B sides (A4_B9 = VBUS,
    # A1_B12 = GND, …) so we wire by pad NUMBER — the symbol's repeated functional
    # names arrive de-duped (VBUS__1, GND__1, SHIELD__1…), so number is the key.
    usb = add_uj20_c_h_g_msmt_1a_p16_tr_67(d, ref="J_USB_C", board_tag="radar_module")
    for nm in ("A4_B9", "B4_A9"):                                 # VBUS
        _net(d, "USB_VBUS").connect(usb.pin(nm))
    for nm in ("A1_B12", "B1_A12", "SH1", "SH2", "SH3", "SH4"):   # GND + shield posts
        _net(d, "GND").connect(usb.pin(nm))
    # CC1/CC2: 5.1 kΩ Rd to GND each → UFP sink presentation (source enables 5 V).
    # CC is a static DC presentation — no SI need to sit by the connector, so the
    # two Rds live on the RADAR (like the IR service-link pair + the OR diode on power_board),
    # keeping the nose_cap to just the connector + its mid-mount cutout. USB_CC1/CC2
    # cross the radar↔nose_cap LGA joint.
    CC_BTAG = "radar_module"
    _net(d, "USB_CC1").connect(usb.pin("A5"))
    res_between(d, "USB_CC1", "GND", "5.1k", ref="R_USB_CC1", board_tag=CC_BTAG)
    _net(d, "USB_CC2").connect(usb.pin("B5"))
    res_between(d, "USB_CC2", "GND", "5.1k", ref="R_USB_CC2", board_tag=CC_BTAG)
    # USB2 D± — tied across both plug orientations → the MP25 USB-FS pair
    _net(d, "USB_DP").connect(usb.pin("A6")); _net(d, "USB_DP").connect(usb.pin("B6"))
    _net(d, "USB_DM").connect(usb.pin("A7")); _net(d, "USB_DM").connect(usb.pin("B7"))
    # SBU1/2 (A8/B8) left unconnected — power + USB2 only.

    # Depot single-cable power: USB 5 V VBUS ORed into BAT_PROT — the protected
    # battery rail that feeds EVERYTHING (PMIC → COMP_5V/COMP_3V3/MP25-core, plus
    # the radar buck + LDO tap BAT_PROT directly), so the depot USB-C runs the
    # FULL unit (NPU + radar), not just a service rail. Q_USB_OR (DMP6110 P-FET
    # ideal diode, 6.5 A) carries it; the binding limit is the ~3 A a non-PD
    # USB-C source can deliver, not the switch. When USB is live it drives
    # BAT_PROT to ≈4.94 V (5 V − 130 mΩ·I, was 5 V − V_F of a Schottky);
    # BAT_PROT > BAT_RAW reverse-biases Q_ISO's body diode (and Q_ISO is force-OFF
    # via the USB interlock), isolating the primary cells (no backfeed, no
    # charging — a Li primary must never be charged). Q_USB_OR's own body diode
    # blocks BAT_PROT from draining into a dead USB line on cell power, with its
    # gate drive unpowered. The OR switch + its VBUS bulk cap
    # live on POWER_BOARD (where BAT_PROT exists) — off the nose_cap — so only
    # USB_VBUS crosses the snake. The nose_cap is now JUST the connector — the
    # CC Rds (above) and the IR service-link pair (below) both live on the radar.
    # The OR switch + VBUS bulk cap + the USB-wake interlock all carry
    # board_tag="power_board" and are authored in build_power_board (the
    # shared power tile must fab identically in EVERY config, USB depot
    # present or not — economies of scale); only USB_VBUS crosses the
    # snake to reach them.

    # ── Nose optical service port — status LEDs RETIRED (2026-07-27) ────────
    # The green/red muzzle LEDs + their MP25 PG7/PG8 sinks are GONE: state
    # and the batt<1h warning are now QUERIED over the IR link (wand asks,
    # round answers) instead of read by eye at the muzzle — power_states §4a.
    # Their slots became the IR pair: D_IR_WAKE (receiver, below) + D_IR_TX.
    #
    # D_IR_TX — VSMB1940X01 940 nm emitter, the TX half of the service link
    # (15 ns die → kbps–MHz OOK; the wand's receiver sets the rate). The
    # drive loop is TILE-LOCAL off BAT_PROT (alive in every state):
    # BAT_PROT → LED → 2× 27 Ω → BSS138 → GND ≈ 44 mA @ 4 V driven rail /
    # ≈ 31 mA @ 3.3 V shelf-diode rail (I_FM abs-max 200 mA; the split
    # current R keeps each 0402 at ~26 mW @ 50 % modulation duty —
    # firmware must cap continuous-ON dwell). Only the logic-level gate
    # net IR_TX crosses the backbone (→ WBA PA6, 3 joints): the WBA keys
    # the emitter from Standby with the MP25 dark, so a wand session — or
    # the bore-side optical downlink, the one channel that escapes a
    # chambered round (Ø30 steel bore is below cutoff at 2.4 GHz) — needs
    # no rail-up. 100 k gate pull-down holds it dark whenever the WBA is
    # unpowered (shelf); C_IR_TX is the local burst reservoir (real part,
    # never ECM-absorbed — it feeds 44 mA edges at the end of the rail).
    LED_BTAG = "radar_module"
    tx = add_vsmb1940x01(d, ref="D_IR_TX", board_tag=LED_BTAG)
    _net(d, "BAT_PROT").connect(tx.pin("A"))
    _net(d, "IR_TX_K") .connect(tx.pin("K"))
    res_between(d, "IR_TX_K", "IR_TX_M", "27",
                ref="R_IR_TX_A", board_tag=LED_BTAG)
    res_between(d, "IR_TX_M", "IR_TX_D", "27",
                ref="R_IR_TX_B", board_tag=LED_BTAG)
    q_irtx = add_bss138lt1g(d, ref="Q_IR_TX", board_tag=LED_BTAG)
    _net(d, "IR_TX_D").connect(q_irtx.pin("3"))   # Drain
    _net(d, "GND")    .connect(q_irtx.pin("2"))   # Source
    _net(d, "IR_TX_G").connect(q_irtx.pin("1"))   # Gate
    res_between(d, "IR_TX",   "IR_TX_G", "100",
                ref="R_IR_TX_G",  board_tag=LED_BTAG)
    res_between(d, "IR_TX_G", "GND",     "100k",
                ref="R_IR_TX_PD", board_tag=LED_BTAG)
    cap_to_gnd(d, "BAT_PROT", "1uF", ref="C_IR_TX", board_tag=LED_BTAG)

    # ── IR activation_unlock wake — VBPW34FAS daylight-filtered PIN photodiode ─────────
    # The optical on-switch (Standby → Ready, the merged staged state):
    # deliberate ~950 nm IR
    # illumination at the nose wakes the WBA55 from Stop1 via EXTI12.
    # Photoconductive mode against RPU_IR_WAKE (470 k → 3V3_AON, lives on
    # wakeup_board beside the WBA — the high-value bias stays OFF this
    # tile so the only long net is the photodiode's own cathode node).
    # Wake needs the node below V_IL ≈ 1 V: (3.3 − 1) / 470 k ≈ 5 µA of
    # photocurrent; the part delivers 45–55 µA at 1 mW/cm² (950 nm,
    # DS 81127) — a close-range IR wand saturates the margin. Sunlight
    # rejection is layered: the package daylight filter (λ < 780 nm
    # blocked), the recessed nose_cap hole's narrow acceptance cone, and
    # a WBA firmware persistence/pattern check (a false wake costs µJ —
    # sample, disqualify, back to Stop1). Zero Standby power adder: the
    # pull-up conducts only when illuminated (dark current 2–30 nA).
    # Light path: nose_cap through-hole relief, auto-generated per F.Cu
    # part (verified by tools/check_nose_cap_cutout.py). This REPLACES the
    # H3LIS motion-detect as the Standby→Ready entry; the H3LIS
    # (now on main 3V3) keeps its launch-witness + flight-recorder
    # roles from Ready on. ⚠ CONOPS: activation_unlock is now a deliberate
    # operator/launcher action — revises the "no launcher cooperation"
    # ground rule in the power_states.md preamble. A round never given IR activation_unlock stays in
    # Standby through launch (no motion fallback any more).
    pd_wake = add_vbpw34fas(d, ref="D_IR_WAKE", board_tag=LED_BTAG)
    _net(d, "IR_WAKE").connect(pd_wake.pin("K"))   # reverse-biased by the pull-up
    _net(d, "GND")    .connect(pd_wake.pin("A"))

    # The aluminium waveguide DISK mounts on the cap's outer face and bears the
    # setback load (not the AWR). The radar couples to it across the air gap over
    # the AWR aperture (no potting in the gap — black Stycast is a 77 GHz
    # absorber). No BLE radiator here (the disk would blind it; the WBA uses the
    # Yagi pair). The aperture is milled by _mark_radar_block_cutout.


# build_nfc_antenna_flex REMOVED 2026-07-30 (NFC subsystem deleted).


def _add_yagi_meander_2g4(d: Design, *, ref: str, board_tag: str,
                          parent_side: str = "S"):
    """Placeholder meandered-Yagi 2.4 GHz flex tile (returns Antenna).

    The fab-ready element geometry (reflector + driven + director(s)
    with a meander pattern that fits λ/2 elements tangentially on a
    Ø34 metal body) is locked by EM simulation — out of scope per the
    plan's "Yagi EM simulation" note. This footprint reserves the tile
    area (20×40 mm rect) and the feed pad; the F.Cu meander pattern
    is a rough placeholder so panel layout, cavity projection, and
    stack-up STEPs all build cleanly while the antenna team works.

    `parent_side` ∈ {"N", "S"} describes where the rigid parent tile
    sits relative to this antenna tile — "S" means the parent is to
    the south, so the feed pad lives on this tile's south edge (the
    one facing the parent). The feed pad spans most of the tile width
    so the flex strip lands ON the pad regardless of where the placer
    routes it. (Before this fix, the pad was a narrow 1.5 × 1.5 mm
    speck at the WRONG edge — the flex was landing on dead copper
    in the middle of the tile.)

    Topology when finalised: boom axial (along the body spin axis,
    pointing aft); elements perpendicular (tangential, meandered into
    ~30 % of λ/2); metal sonde body acts as the back-reflector that
    improves the front-to-back ratio.
    """
    W = 20.0      # tile tangential extent
    L = 40.0      # tile axial extent (boom direction)
    # Courtyard padding is zero: the chip's body IS the tile body
    # (the flex IS the antenna), so the packer's "chip fully inside
    # outline" check needs equal extents. A non-zero crt would push
    # the chip's bbox by 2·crt > tile, the packer falls back to
    # (100, 0), and the antenna renders 100 mm off-tile.
    crt = 0.0

    # Feed pad on the edge facing the parent. Tile-local Smash y is
    # negated on KiCad export, so a tile-local Smash y of -18.5 lands
    # at panel +18.5 in KiCad coords (the +y / south-on-screen edge of
    # the tile body) — which is the edge facing a parent that sits
    # south of this tile (`parent_side="S"`). And vice-versa.
    if parent_side == "S":
        feed_y = -L / 2 + 1.5     # Smash y = south edge of tile
    elif parent_side == "N":
        feed_y = +L / 2 - 1.5
    else:
        raise ValueError(f"parent_side must be 'N' or 'S', got {parent_side!r}")
    feed_xy = (0.0, feed_y)
    feed_pad = Pad(num="1", position_mm=feed_xy,
                   size_mm=(W - 2.0, 1.5), shape="rect", layer="F.Cu")

    # Boom runs the long axis, AWAY from the feed edge into the tile.
    # sign = +1 when feed is at -y, so boom progresses through +y.
    sign = +1.0 if parent_side == "S" else -1.0
    driven_y = feed_y + sign * 4.0
    # Reflector behind the driven (toward feed edge); directors ahead.
    # 8 mm spacing — calibrated so all elements stay inside the body
    # rectangle [-20, +20] regardless of boom orientation.
    element_offsets = [-3.5, 0.0, +8.0, +16.0]
    #                 (reflector, driven, dir1, dir2 — relative offset
    #                  from driven along the boom direction)
    elements_y = [driven_y + sign * dy for dy in element_offsets]

    placeholder_traces = []
    for y in elements_y:
        # Each element is a horizontal trace of meander-equivalent
        # length; the real meander zigzag replaces this in fab.
        placeholder_traces.append({
            "layer": "F.Cu",
            "width_mm": 0.3,
            "points": [(-W / 2 + 2.0, y), (W / 2 - 2.0, y)],
        })
    # Feed line from the feed pad inward to the driven element.
    placeholder_traces.append({
        "layer": "F.Cu",
        "width_mm": 0.5,
        "points": [feed_xy, (0.0, driven_y)],
    })

    fp = Footprint(
        name="Yagi_Meander_Flex_2G4",
        package_class="Flex-tile meandered Yagi (placeholder)",
        pads=[feed_pad],
        copper_lines=placeholder_traces,
        body_outline=[(-W/2, -L/2), (+W/2, -L/2),
                      (+W/2, +L/2), (-W/2, +L/2)],
        courtyard=[(-W/2 - crt, -L/2 - crt), (+W/2 + crt, -L/2 - crt),
                   (+W/2 + crt, +L/2 + crt), (-W/2 - crt, +L/2 + crt)],
        size_mm=(W, L),
        height_mm=0.1,
        source="project",
    )
    return d.add_antenna(
        ref=ref, manf_pn=None, footprint=fp, board_tag=board_tag,
        name="YAGI_MEANDER_FLEX_2G4",
        description=(
            "2.4 GHz meandered-Yagi printed on polyimide flex "
            "(placeholder). Boom axial along the body spin axis (aft-"
            "pointing); elements tangential, meandered into ~30 % of "
            "λ/2; metal sonde body is the back-reflector. Endfire "
            "backward toward the launch point. Fab-ready element "
            "geometry pending EM simulation."),
        frequency_band_hz=(2.4e9, 2.485e9),
        centre_frequency_hz=2.442e9,
        bandwidth_hz=85e6,
        polarization="linear",          # CP comes from the on-board
                                        # Wilkinson + 90° hybrid combining
                                        # this antenna with its 90°-offset
                                        # partner (yagi_b), so EACH tile
                                        # is linearly polarised
        pattern="yagi-uda",
        peak_gain_dbi=5.0,
        front_to_back_db=8.0,
        half_power_beamwidth_deg=60.0,
        efficiency=0.45,                # meandering costs efficiency
        impedance_ohm=50.0,
        vswr_max=2.0,
        package="printed-flex Yagi",
        size_mm=(W, L), height_mm=0.1,
        body_material="polyimide flex",
        weight_g=0.02,
        pins=[Pin(num="1", name="FEED", type="passive")],
    )


def build_yagi_antenna_a_flex(d: Design) -> None:
    """Yagi-A 2.4 GHz meandered flex. Branches off wakeup_board's
    NORTH edge (back with the WBA since 2026-07-31), so Yagi-A's parent
    sits to the SOUTH of the tile and the feed pad lives on the tile's
    south edge — the one facing the rigid-flex transition to
    wakeup_board. Feed pad sees `YAGI_RF_A` (driven by WBA RF →
    π-match → Wilkinson → 90° hybrid on wakeup_board). Not in
    core_radar (RF-dark: the leaf is dropped, the parent stays)."""
    ant = _add_yagi_meander_2g4(
        d, ref="ANT_YAGI_A", board_tag="yagi_ant_a_flex",
        parent_side="S")
    _net(d, "YAGI_RF_A").connect(ant.pin("1"))


def build_yagi_antenna_b_flex(d: Design) -> None:
    """Yagi-B 2.4 GHz meandered flex — CP partner to Yagi-A. Branches
    off wakeup_board's SOUTH edge (back with the WBA since 2026-07-31;
    90° opposite from Yagi-A on the body meridians), so its parent is
    to the NORTH and the feed pad lives on the tile's north edge facing
    wakeup_board. Fed 90° out of phase with Yagi-A via the on-board
    hybrid coupler → circular polarisation on the backward beam,
    spin-immune. Not in core_radar (RF-dark: the leaf is dropped, the
    parent stays)."""
    ant = _add_yagi_meander_2g4(
        d, ref="ANT_YAGI_B", board_tag="yagi_ant_b_flex",
        parent_side="N")
    _net(d, "YAGI_RF_B").connect(ant.pin("1"))


def build_spacers(d: Design, boards: dict | None = None) -> None:
    """One mechanical spacer disc per accordion-fold gap. Each is a Ø34 mm
    rigid PCB disc with chip-clearance cavities milled on both faces.
    Pin 1 ties to GND just to give the netlist a connection (no real
    electrical function).

    Panel-driven: the snake order (and therefore which board pairs are
    adjacent) comes from the fold solver, so we create a spacer chip for
    every spacer Board the panel produced rather than a hard-coded pair
    list. `boards` defaults to a fresh `build_panel()` (deterministic, so
    the spacer board_tags match). Mirrors system.py:add_spacer_boards."""
    if boards is None:
        _panel, boards = build_panel()
    spacer_boards = [b for b in boards.values()
                     if getattr(b, "kind", None) == "spacer"]
    for sp_board in spacer_boards:
        # Ref derives from the spacer NAME, not creation order — a config
        # with fewer spacers must still emit the identical scaffold chip
        # per shared spacer (economies of scale; was SP1..SPn positional).
        sp = add_mechanical_spacer_34mm(
            d, ref="SP_" + sp_board.name.removeprefix("spacer_"),
            board_tag=sp_board.name,
            value=sp_board.name.upper(), manf_pn=None,
            description=(
                f"Mechanical spacer {sp_board.name} — Ø34 mm rigid "
                "interposer, cavities milled for chips on both adjacent "
                "tile faces. No signals."))
        _net(d, "GND").connect(sp.pin("1"))


def build_flight_board(d: Design, board_tag: str = "flight_board") -> None:
    """IMU / magnetometer sensor cluster. As of the wakeup+flight consolidation
    this FOLDS INTO wakeup_board: build_wakeup_board calls it with
    board_tag="wakeup_board". The two aft tiles merged because each was left with
    only a handful of chips once flight control moved onto the MP25 Cortex-M33.
    The default board_tag="flight_board" keeps the standalone Ø34 tile available
    as a test fixture (and for any config that still folds it separately).

    Builds on `board_tag`: IIS2MDC magnetometer + 3x ISM330DHCX IMU on I2C2/3,
    their pull-ups + the SYS_I2C pull-ups, and the flex-bus alias merges. Two
    blocks created here are tagged to their OWN tiles (placement follows the tag,
    not `board_tag`): the EXT_CAN TCAN1042 (aft_end_board, by the TP_CAN pads)
    and the 4 QPD transimpedance amps (qpd_module, behind the photodiode). The
    launch-detect comparator itself lives on fin_ble_board (by the piezo)."""
    BTAG = board_tag

    # ── System control bus pull-ups (SYS_I2C; the M33 is master) ─────
    # (boot-transient pre-charge through the MP25 TT clamps — see the
    # rule-sweep F5 note at the I2C2/3 pull-ups)
    res_between(d, "3V3", "SYS_I2C_SCL", "4.7k", ref="RPU_SCL_EXT", board_tag=BTAG)
    res_between(d, "3V3", "SYS_I2C_SDA", "4.7k", ref="RPU_SDA_EXT", board_tag=BTAG)

    # ── EXT_CAN transceiver (TCAN1042) — re-homed here from companion_compute ──
    # The MP25 FDCAN1 controller (EXT_CAN_TX/RX) drives this PHY across the
    # LGA backbone; CANH/CANL are exposed at the TP_CAN_P/N pogo pads on
    # aft_end's service face. Moved off companion_compute to free top-face
    # area for the un-rotated DDR4 + the two SPI-NAND dies; moved again
    # activation→aft_end 2026-07-31 (activation chip redistribution): the PHY
    # + its 120 Ω terminator now sit directly at the CAN pads (CANH/CANL are
    # local vias), and only the digital TXD/RXD cross up to the MP25 FDCAN1.
    # (Code lives here in build_flight_board for now; placement follows
    # board_tag.)
    _CAN_TAG = "aft_end_board"
    can_gw = add_tcan1042gvdq1(d, ref="U_CAN_GW", board_tag=_CAN_TAG)
    _net(d, "EXT_CAN_TX").connect(can_gw.pin("TXD"))
    _net(d, "EXT_CAN_RX").connect(can_gw.pin("RXD"))
    _net(d, "GND").connect(can_gw.pin("GND"))
    # VCC needs 4.5-5.5 V (SLLSES9D §7.4 — the GV variant UVLOs below
    # that, so a 3V3-fed PHY sits in protected mode = bus dead). COMP_5V
    # extends aft down the whole column (wakeup → activation → the battery
    # spacers → aft_end) to feed it; VIO
    # stays on 3V3 (3-5.5 V) level-shifting TXD/RXD to the MP25's 3.3 V
    # FDCAN logic — exactly the split the V variant exists for. CAN is
    # alive only while the COMP boost runs, which is fine: the MP25 (the
    # only FDCAN controller) is only alive then too.
    # Rail-audit disposition (2026-06-11): COMP_5V spanning power→wakeup→
    # activation is DELIBERATE — retraction via a 3.3 V CAN PHY was
    # considered and dropped; a high-power line through the whole stack
    # is worth the 4 lands (future loads tap it without re-plumbing).
    _net(d, "COMP_5V").connect(can_gw.pin("VCC"))
    _net(d, "3V3").connect(can_gw.pin("VIO"))
    _net(d, "GND").connect(can_gw.pin("STB"))        # high-speed mode
    _net(d, "EXT_CAN_P").connect(can_gw.pin("CANH"))
    _net(d, "EXT_CAN_N").connect(can_gw.pin("CANL"))
    cap_to_gnd(d, "COMP_5V", "100nF", ref="C_CAN_GW",
               embedded_cap_absorbs=True, board_tag=_CAN_TAG)
    res_between(d, "EXT_CAN_P", "EXT_CAN_N", "120",
                ref="R_EXT_CAN_TERM", board_tag=_CAN_TAG)

    # ── IIS2MDC magnetometer on I2C2 (DRDY -> M33 EXTI) ──────────────
    mag = add_iis2mdctr(d, ref="U_MAG", board_tag=BTAG)
    _net(d, "3V3")     .connect(mag.pin("VDD"))
    _net(d, "3V3")     .connect(mag.pin("VDD_IO"))
    _net(d, "GND")     .connect(mag.pin("GND_1"))
    _net(d, "GND")     .connect(mag.pin("GND_2"))
    _net(d, "I2C2_SCL").connect(mag.pin("SCL"))
    _net(d, "I2C2_SDA").connect(mag.pin("SDA"))
    _net(d, "MAG_DRDY").connect(mag.pin("INT_DRDY"))
    _net(d, "3V3")     .connect(mag.pin("CS"))    # high -> I2C mode
    _net(d, "MAG_C1_TERM").connect(mag.pin("C1"))
    # 220 nF per IIS2MDC DS Table (set/reset reservoir, voltage forced by
    # the device): low ESR (≤200 mΩ), tight to pins 5/6 — a REAL discrete,
    # never ECM-absorbed (private node, not a rail).
    cap_to_gnd(d, "MAG_C1_TERM", "220nF", ref="C_MAG_C1", board_tag=BTAG)
    cap_to_gnd(d, "3V3", "100nF", ref="C_MAG1", embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "3V3", "1uF",   ref="C_MAG2", board_tag=BTAG)
    tp_drdy = _add_testpoint(d, ref="TP_MAG_DRDY", board_tag=BTAG)
    _net(d, "MAG_DRDY").connect(tp_drdy.pin("1"))

    # ── I2C2/3 pull-ups ──────────────────────────────────────────────
    # Two sensor I2C buses (was three) — frees 2 LGA lands on the tight
    # companion↔flight joint for the depot USB pair, keeping all 3 IMUs.
    # ⚠ rule-sweep F5 (boot transient, ACCEPTED): 3V3 rises at QMAIN
    # while the MP25's VDDIO (COMP_3V3 = PMIC BUCK2, rank 1) is still
    # down, so for the few PMIC-boot ms every 3V3 pull that reaches an
    # MP25 TT pin (I2C2/3, SYS_I2C, PMIC INTN) pre-charges COMP_3V3
    # through the TT clamp (~0.6 mA/line, ~4 mA total). Within the TT
    # injection limits and the STPMIC25 bucks are pre-bias safe.
    # BRING-UP: scope COMP_3V3 pre-bias at main-switch turn-on.
    for bus in ("I2C2", "I2C3"):
        res_between(d, "3V3", f"{bus}_SCL", "4.7k", ref=f"RPU_{bus}_SCL", board_tag=BTAG)
        res_between(d, "3V3", f"{bus}_SDA", "4.7k", ref=f"RPU_{bus}_SDA", board_tag=BTAG)

    # ── 3x ISM330DHCX IMU (INT1 -> M33 EXTI) ────────────────────────
    # I2C2: mag (0x1E) + IMU1 (SA0=0). I2C3: IMU2 (SA0=0) + IMU3 (SA0=1) —
    # distinct addresses per bus; two independent buses still isolate a fault.
    for idx, scl, sda, sa0 in [(1, "I2C2_SCL", "I2C2_SDA", "GND"),
                               (2, "I2C3_SCL", "I2C3_SDA", "GND"),
                               (3, "I2C3_SCL", "I2C3_SDA", "3V3")]:
        imu = add_ism330dhcxtr(d, ref=f"U_IMU{idx}", board_tag=BTAG)
        _net(d, "3V3").connect(imu.pin("VDD"))
        _net(d, "3V3").connect(imu.pin("VDDIO"))
        _net(d, "GND").connect(imu.pin("GND_1"))
        _net(d, "GND").connect(imu.pin("GND_2"))
        _net(d, scl).connect(imu.pin("SCL"))
        _net(d, sda).connect(imu.pin("SDA"))
        _net(d, "3V3").connect(imu.pin("CS"))
        _net(d, f"IMU{idx}_INT") .connect(imu.pin("INT1"))
        _net(d, f"IMU{idx}_INT2").connect(imu.pin("INT2"))
        _net(d, sa0).connect(imu.pin("SA0"))
        _net(d, f"IMU{idx}_SCX").connect(imu.pin("SCX"))
        _net(d, f"IMU{idx}_SDX").connect(imu.pin("SDX"))
        res_between(d, "3V3", f"IMU{idx}_SCX", "10k", ref=f"R_IMU{idx}_SCX_PU", board_tag=BTAG)
        res_between(d, "3V3", f"IMU{idx}_SDX", "10k", ref=f"R_IMU{idx}_SDX_PU", board_tag=BTAG)
        # Aux-SPI unused — DS13012 pin table: OCS_Aux "leave unconnected"
        # (it's the aux-interface enable; the old GND tie was an
        # unsanctioned strap), SDO_Aux "connect to Vdd_IO or leave
        # unconnected" (GND not allowed). Both left floating.
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_IMU{idx}_1", embedded_cap_absorbs=True, board_tag=BTAG)
        cap_to_gnd(d, "3V3", "2.2uF", ref=f"C_IMU{idx}_2", board_tag=BTAG)
        cap_to_gnd(d, "3V3", "10nF",  ref=f"C_IMU{idx}_3", embedded_cap_absorbs=True, board_tag=BTAG)
        tp_int = _add_testpoint(d, ref=f"TP_IMU{idx}_INT", board_tag=BTAG)
        _net(d, f"IMU{idx}_INT").connect(tp_int.pin("1"))

    # ── flex bus alias merges (FLEX_* -> rigid rails; bench I2C -> SYS_I2C) ─
    d.merge_nets("FLEX_GND", "GND")
    d.merge_nets("3V3", "FLEX_3V3")
    d.merge_nets("SYS_I2C_SCL", "FLEX_I2C_SCL")
    d.merge_nets("SYS_I2C_SDA", "FLEX_I2C_SDA")
    cap_to_gnd(d, "COMP_1V8", "100nF", ref="C_CAM_VDD", embedded_cap_absorbs=True, board_tag=BTAG)

    # Launch detect (piezo comparator) lives on fin_ble_board — it sits by
    # the piezo disk (the battery-compartment ceiling's top face since the
    # 2026-07-31 stack reorder) so the high-Z analog stays local; only the
    # digital COMP_OUT crosses to the M33 PD5 EXTI. The hardware confirm
    # AND-gate is retired: ACTIVATE_SET / ACTIVATE_CONFIRM are firmware GPIOs.

    # ── 4x AD8603 QPD transimpedance amps (board_tag=qpd_module, bottom face — directly behind the photodiode so
    # the high-Z anode->TIA node is microscopic; TIA outputs ride the branch to ADC) ────────
    # QPD_VREF (mid-rail 1.65 V) is BOTH the TIAs' +IN reference AND the
    # photodiode common-cathode return (build_qpd_module), so every quadrant
    # sits at true zero bias (photovoltaic). Outputs idle at 1.65 V and swing
    # DOWN with light: Vout = VREF − Ip·Rf, 1.65 µA full scale per quadrant.
    # The divider's 50 kΩ Thevenin carries the summed photocurrents — pulsed
    # content rides the 1 µF; stiffen/buffer if DC accuracy ever matters.
    res_between(d, "3V3",      "QPD_VREF", "100k", ref="R_QPD_VREF_H", board_tag="qpd_module")
    res_between(d, "QPD_VREF", "GND",      "100k", ref="R_QPD_VREF_L", board_tag="qpd_module")
    cap_to_gnd(d, "QPD_VREF", "1uF",   ref="C_QPD_VREF1", board_tag="qpd_module")
    cap_to_gnd(d, "QPD_VREF", "100nF", ref="C_QPD_VREF2", board_tag="qpd_module")
    for ch, qpd_in_net, tia_out_net in [("A", "QPD_A", "QPD_TIA_A"),
                                        ("B", "QPD_B", "QPD_TIA_B"),
                                        ("C", "QPD_C", "QPD_TIA_C"),
                                        ("D", "QPD_D", "QPD_TIA_D")]:
        res_between(d, qpd_in_net, tia_out_net, "1M", ref=f"R_TIA_{ch}", board_tag="qpd_module")
        # Cf = 8.2 pF for TIA stability: at zero bias the MT03-092 quadrant is
        # ~140 pF (DS, VR=0), and Cf_opt ≈ sqrt(Cin/(2π·Rf·GBP)) =
        # sqrt(140p/(2π·1M·400k)) ≈ 7.5 pF — the old 1 pF left the noise-gain
        # crossing badly underdamped (ringing). BW = 1/(2π·1M·8.2p) ≈ 19 kHz:
        # a charge-integrating pulse detector, consistent with the AD8603's
        # 400 kHz GBP
        cap_fb = add_capacitor_c0g_0603_avx_sqcs(d, ref=f"C_TIA_{ch}", value="8.2pF", board_tag="qpd_module")
        _net(d, qpd_in_net) .connect(cap_fb.pin("1"))
        _net(d, tia_out_net).connect(cap_fb.pin("2"))
        opa = add_ad8603aujz_r2_single_supply(d, ref=f"U_TIA_{ch}", board_tag="qpd_module")
        _net(d, qpd_in_net) .connect(opa.pin("-IN"))
        _net(d, "GND")      .connect(opa.pin("V-"))
        _net(d, "QPD_VREF") .connect(opa.pin("+IN"))
        _net(d, tia_out_net).connect(opa.pin("OUT"))
        _net(d, "3V3")      .connect(opa.pin("V+"))
        cap_to_gnd(d, "3V3", "100nF", ref=f"C_TIA_{ch}_PWR", embedded_cap_absorbs=True, board_tag="qpd_module")

    # (Radar power switch deleted — the AWR's buck + LDO now tap always-on
    # BAT_PROT directly and self-gate via their EN pins tied to RADAR_EN; the
    # gating + the RADAR_EN pull-down live on radar_module. flight is pure sensors.)


def build_power_board(d: Design) -> None:
    """Power tile — concentrates the power conversion stack between
    activation_interface (cells) and wakeup_board:
      - 3× TLM-1520HPM/S cells via CellAttach pads + 200 mΩ iso resistors
      - Q_ISO nanopower ideal-diode reverse-block (BAT_RAW → BAT_PROT;
        replaces the TPS25940 eFuse — kills the ~10 µA shelf floor)
      - TPS61175 boost reg (REG_IN_MAIN → COMP_5V ≈ 5.03 V, feeds PMIC + fins)
      - STPMIC25APQR PMIC (COMP_5V → 0V9 / 1V8 / 1V2 / 2V8 / VPP 2.5 rails)
      (the separate companion-3V3 LDO is gone — the single 3V3 rail from
       wakeup_board now feeds the companion's 3.3 V loads too)
      - Optional dedicated camera LDOs (DNP; LP5907 ×2 for VAA / VDD)
      - TMP117 precision temp sensor on I2C2 (hottest tile)

    Mirrors system.py boards 4627–4642 (between `_BOARD_TAG=power_board`
    and the wakeup_board transition).
    """
    BTAG = "power_board"

    # ── battery cells + contacts (mode = module global _BATTERY_MODE) ─
    # The cells use factory-welded SIDE solder tabs (no end pins — the old
    # pinned-contact scheme is gone, 2026-07-30). Triple: cells stand in the
    # compartment between the THIN cell_floor_board and fin_ble_board (the
    # ceiling since the 2026-07-31 stack reorder — activation_interface
    # moved down between aft_end and cell_floor). Single: the one horizontal
    # cell lies on aft_end_board (no floor tile). Only the tab-landing pads
    # (+ iso resistors, triple mode) live on the tiles.
    if _BATTERY_MODE == "single":
        # opt-in (core_1cell): ONE horizontal TLM-1530M/S laid flat on
        # aft_end_board. Both side-tab lands are on that tile; + → BAT_RAW
        # directly (single cell ⇒ no isolation resistor), − → GND. The Battery
        # record carries the 200 mAh / $61.52 / 12 g for the BOM (no footprint
        # — see the tab lands).
        add_tlm_1530m(d, ref="BT_CELL")   # BOM record only — cell sits in the compartment, not placed on a board
        # Two DISCRETE side solder-tab lands (placeholder footprint) at the
        # cell ends, locked on the N–S cell axis. Replaces the old single 2-pad
        # P_CELL_CONTACTS_1H, whose 27 mm span reserved the whole board centre.
        pos = add_cell_solder_tab(d, ref="P_CELL_TAB_POS", board_tag="aft_end_board")
        neg = add_cell_solder_tab(d, ref="P_CELL_TAB_NEG", board_tag="aft_end_board")
        _net(d, "BAT_RAW").connect(pos.pin("1"))  # cell +
        _net(d, "GND").connect(neg.pin("1"))      # cell −
    else:
        # DEFAULT: 3× TLM-1520HPM/S stood VERTICAL, triangle around the spin
        # axis, bases flat on cell_floor_board. + tab lands on
        # fin_ble_board's bottom face (one per cell, at the cell centres —
        # the compartment ceiling), − side tabs bend down to three discrete
        # lands on cell_floor_board inside the cell bore circles (locked —
        # battery-facing faces keep everything inside the 3 bores so the
        # compartment spacers give up no extra cutout), each
        # + → 200 mΩ iso resistor → BAT_RAW.
        # (The cells themselves are not board-tagged parts, just the pads +
        # iso resistors.)
        contacts = add_cell_contacts_3(d, ref="P_CELL_CONTACTS",
                                       board_tag="fin_ble_board")
        _net(d, "BAT_CELL1_POS").connect(contacts.pin("1"))
        _net(d, "BAT_CELL2_POS").connect(contacts.pin("2"))
        _net(d, "BAT_CELL3_POS").connect(contacts.pin("3"))
        for _k in (1, 2, 3):
            tab = add_cell_solder_tab(d, ref=f"P_CELL_TAB_NEG{_k}",
                                      board_tag="cell_floor_board")
            _net(d, "GND").connect(tab.pin("1"))

    # The 3× 200 mΩ iso resistors are UNCONDITIONAL: power_board is a
    # shared part across every config (economies of scale), so its copper
    # must not depend on the battery mode. In single mode the BAT_CELLx_POS
    # nets are stubs (the cell + ties to BAT_RAW at the aft_end tab) — the
    # resistors fab anyway, DNP at assembly.
    res_between(d, "BAT_CELL1_POS", "BAT_RAW", "200m",
                ref="R_BAT1_ISO", board_tag=BTAG)
    res_between(d, "BAT_CELL2_POS", "BAT_RAW", "200m",
                ref="R_BAT2_ISO", board_tag=BTAG)
    res_between(d, "BAT_CELL3_POS", "BAT_RAW", "200m",
                ref="R_BAT3_ISO", board_tag=BTAG)

    # ── BAT_RAW bulk caps + nanopower ideal-diode reverse-block ──────
    # The TPS25940 eFuse was REMOVED (2026-06). Its IQ(OFF) ≈ 9-15 µA sat
    # on the always-live cell rail and WAS the entire ~10 µA shelf floor,
    # dragging the 200 mAh cell's shelf life to ~2 y when the chemistry
    # alone supports ~20 y (datasheet self-discharge ~3 %/yr). The eFuse
    # earned its place by three jobs: (1) reverse-block depot-USB out of
    # the Li primary (a primary must NEVER be back-fed), (2) 5 A
    # overcurrent trip, (3) IMON/PGOOD/FLT telemetry. (2) and (3) are
    # dropped — the TLM-1530M/S passes Tadiran's external-short safety
    # test, so an unprotected short does not vent — and (1), the safety-
    # critical one, is kept as a nanopower P-FET ideal diode (Q_ISO).
    cap_to_gnd(d, "BAT_RAW", "470uF", ref="C_BAT_BULK1", board_tag=BTAG)
    cap_to_gnd(d, "BAT_RAW", "470uF", ref="C_BAT_BULK2", board_tag=BTAG)

    # Q_ISO — ideal-diode reverse-block, BAT_RAW (cell) → BAT_PROT (load /
    # USB-OR point). Body diode (drain=BAT_RAW → source=BAT_PROT) passes
    # the cell FORWARD and BLOCKS BAT_PROT→cell, so depot USB (≈4.94 V on
    # BAT_PROT via the Q_USB_OR ideal diode) cannot charge the primary.
    # Default OFF (gate≈source via R_ISO_H, V_GS≈0) → body-diode-only,
    # ~nA reverse leakage → NANOPOWER shelf, no IQ on the cell. Firmware
    # pulls it fully ON in flight (BAT_ISO_EN) for a low-drop forward
    # path; depot-USB force-OFF is a HARDWARE interlock (Q_ISO_USB),
    # independent of firmware. DMP6110: -60 V, 6.5 A cont — carries the
    # whole pack (the radar taps BAT_PROT downstream of this, ahead of
    # QMAIN). Same high-side P-FET + NFET gate-pull idiom as Q_ACTIVATION_UNLOCK.
    # NOTE: forward-drop, gate-drive timing and the USB interlock want
    # bench/sim confirmation before fab (analog behaviour, not modelled
    # by the connectivity build).
    q_iso = add_dmp6110svt_7(d, ref="Q_ISO", board_tag=BTAG)
    for dp in ("D_1", "D_2", "D_3", "D_4"):
        _net(d, "BAT_RAW").connect(q_iso.pin(dp))      # drains → cell side
    _net(d, "BAT_PROT") .connect(q_iso.pin("S"))       # source → load / USB side
    _net(d, "BAT_ISO_G").connect(q_iso.pin("G"))
    # Gate divider: BAT_PROT ─100k─ G ─10k─ Q_ISO_DRV drain. DRV off →
    # G≈BAT_PROT (V_GS≈0, OFF, nanopower). DRV on → G≈BAT_PROT·10/110
    # ≈0.4 V → V_GS≈-3.6 V (fully on, within ±20 V V_GSS).
    res_between(d, "BAT_PROT",  "BAT_ISO_G",  "100k", ref="R_ISO_H", board_tag=BTAG)
    res_between(d, "BAT_ISO_G", "BAT_ISO_GD", "10k",  ref="R_ISO_L", board_tag=BTAG)
    q_iso_drv = add_bss138lt1g(d, ref="Q_ISO_DRV", board_tag=BTAG)
    _net(d, "BAT_ISO_GD").connect(q_iso_drv.pin("3"))   # drain → gate divider
    _net(d, "GND")       .connect(q_iso_drv.pin("2"))   # source
    _net(d, "BAT_ISO_EN").connect(q_iso_drv.pin("1"))   # gate (driven via R_ISO_EN_S)
    res_between(d, "BAT_ISO_EN", "GND", "100k", ref="R_ISO_EN_PD", board_tag=BTAG)
    # SAFETY: BAT_ISO_EN is driven from the MP25 GPIO through a 10k SERIES R so
    # the hardware USB interlock below ALWAYS wins — Q_ISO_USB (RDS ~Ω) sinks
    # BAT_ISO_EN to GND even against a push-pull GPIO driving high through 10k
    # (contention bounded to ~0.33 mA). A primary cell must never be back-fed,
    # so firmware MUST NOT be able to override the interlock.
    res_between(d, "BAT_ISO_DRIVE", "BAT_ISO_EN", "10k", ref="R_ISO_EN_S", board_tag=BTAG)
    # Depot-USB hardware interlock: VBUS present → Q_ISO_USB pulls BAT_ISO_EN
    # low → Q_ISO OFF → body diode reverse-blocks → cell isolated, regardless
    # of (and overriding) firmware. The body diode is the unconditional backstop;
    # this interlock only matters in the one window where firmware has turned the
    # channel ON (low-drop forward) and USB is then plugged.
    q_iso_usb = add_bss138lt1g(d, ref="Q_ISO_USB", board_tag=BTAG)
    _net(d, "BAT_ISO_EN")  .connect(q_iso_usb.pin("3"))   # drain → force EN low
    _net(d, "GND")         .connect(q_iso_usb.pin("2"))   # source
    _net(d, "BAT_ISO_USBG").connect(q_iso_usb.pin("1"))   # gate
    res_between(d, "USB_VBUS",      "BAT_ISO_USBG", "100k", ref="R_ISO_USB_H", board_tag=BTAG)
    res_between(d, "BAT_ISO_USBG",  "GND",          "100k", ref="R_ISO_USB_L", board_tag=BTAG)

    cap_to_gnd(d, "BAT_PROT", "100uF", ref="CBAT1", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "100uF", ref="CBAT2", board_tag=BTAG)
    cap_to_gnd(d, "BAT_PROT", "1uF",   ref="CBAT3", board_tag=BTAG)

    # ── add_companion_power — ONE shared 5 V boost (PMIC + fins) ─────
    # Merged: this boost replaces the separate fins U_FINBOOST — it now feeds the
    # PMIC (MP25) AND the 4 DRV8428E fin drivers (which tap COMP_5V_RAW one gap
    # away). TPS61175 (3 A min switch limit, SLVS892F) — upsized 2026-06-11
    # from the 2 A TPS61085 (rail-audit item; combined load ~2–2.5 A pk @ 5 V).
    # Continuous capability IOUT(max) = VIN·ILIM·(1−ΔI/2)·η/VOUT ≈ 1.55 A at
    # VIN=3.0 V → ~2.2 A at 4.2 V (DS Eq.8); fin VM pulses above that ride the
    # ~70 µF output bank (C_BOOST_OUT* + C_FIN_VM_BULK + LC-side caps).
    # The fins sit on COMP_5V_RAW (boost output, noisy side); an LC filter
    # (L_PMIC_FILT) isolates the PMIC's COMP_5V so motor switching doesn't
    # reach the MP25 core rails.
    # feature="bottom": the HTSSOP-14 body (4.4×5.0 vs the old TSSOP-8's
    # 3.0×4.4) overflows the saturated power↔companion joint by 5 lands in
    # core_radar — bottom face also co-locates it with L_BOOST_COMP (tight
    # SW loop on one face).
    boost = add_tps61175pwpr(d, ref="U_COMP_BOOST", board_tag=BTAG,
                             feature="bottom")
    _net(d, "REG_IN_MAIN") .connect(boost.pin("VIN"))     # 3
    _net(d, "COMP_5V_SW")  .connect(boost.pin("SW_1"))    # 1 ┐ switch node
    _net(d, "COMP_5V_SW")  .connect(boost.pin("SW_2"))    # 2 ┘
    _net(d, "COMP_5V_FB")  .connect(boost.pin("FB"))      # 9
    _net(d, "GND")         .connect(boost.pin("PGND_1"))  # 12
    _net(d, "GND")         .connect(boost.pin("PGND_2"))  # 13
    _net(d, "GND")         .connect(boost.pin("PGND_3"))  # 14
    _net(d, "GND")         .connect(boost.pin("AGND"))    # 7
    _net(d, "GND")         .connect(boost.pin("EP"))      # 15 thermal pad → GND plane vias
    _net(d, "GND")         .connect(boost.pin("NC"))      # 11 DS: "Reserved. Must connect to ground."
    _net(d, "GND")         .connect(boost.pin("SYNC"))    # 6 internal osc — DS: tie to AGND when unused
    _net(d, "REG_IN_MAIN") .connect(boost.pin("EN"))      # 4 (always-on, follows the main switch)
    _net(d, "COMP_5V_COMP").connect(boost.pin("COMP"))    # 8
    # fSW = 600 kHz via R_FREQ = 176 k (DS Table 2) — matched to the 10 µH
    # inductor: ΔI_L ≈ 0.2 A (~12 % ripple) keeps a usable current-sense
    # ramp; at 1.2 MHz the same L leaves ~6 % and the DS warns internal-osc
    # pulse-skipping above 1.2 MHz anyway. FREQ must never be left open.
    _net(d, "COMP_5V_FREQ").connect(boost.pin("FREQ"))    # 10
    res_between(d, "COMP_5V_FREQ", "GND", "176k",
                ref="R_BOOST_FREQ", board_tag=BTAG)
    # Soft-start 47 nF (DS §7.3.2: "eliminates the output overshoot ... for
    # most applications") — closes the rail-audit inrush item: the PMIC +
    # 47 µF + fin bulk downstream of QMAIN were unmanaged with the 61085's
    # open SS pin.
    _net(d, "COMP_5V_SS")  .connect(boost.pin("SS"))      # 5
    cap_to_gnd(d, "COMP_5V_SS", "47nF", ref="C_BOOST_SS", board_tag=BTAG)

    # Boost topology per DS §Typical Application (non-synchronous):
    # inductor IN → SW, Schottky rectifier SW → VOUT.
    # WE-PD 744043100 10 µH / Isat 6 A (inside the DS 4.7–47 µH window,
    # §6.3) replaces the Isat-marginal 1.2 A TMS 2.2 µH. 4.8×4.8×2.8 mm
    # body goes on the bottom (wakeup-facing) face: the power↔companion
    # joint face is saturated (see L_PMIC_BUCK5) and must not grow.
    l_boost = add_we_744043100(d, ref="L_BOOST_COMP", board_tag=BTAG,
                               feature="bottom")
    _net(d, "REG_IN_MAIN").connect(l_boost.pin("1"))
    _net(d, "COMP_5V_SW") .connect(l_boost.pin("2"))
    # PMEG040V050EPE-QZ 5 A/40 V low-V_F Schottky (was an MBRS540T3G in SMC
    # until 2026-09-02): diode average current = IOUT (≤ ~2.2 A) but fin-pulse
    # peaks track the 3.8 A typ switch limit, so the 5 A envelope stays.
    # A non-synchronous boost NEEDS a rectifier diode — the TPS61175 carries
    # only the low-side switch — so unlike the depot-USB OR this cannot become
    # an ideal-diode FET. The swap is about HEIGHT: CFP15B is 1.1 mm against
    # the SMC's 2.56 mm, and the SMC was the single part on this face driving
    # the power↔companion spacer past what the rest of the gap needs (see
    # spacer_sizing). Same 40 V/5 A, same drop (520 vs 500 mV max at 5 A),
    # lower leakage, 175 °C T_j, AEC-Q101. Pins 1+2 are both anode (tie both
    # — the clip-bond package splits the anode across two leads), 3 = cathode.
    d_boost = add_pmeg040v050epe_qz(d, ref="D_BOOST_COMP", board_tag=BTAG)
    _net(d, "COMP_5V_SW") .connect(d_boost.pin("A_1"))
    _net(d, "COMP_5V_SW") .connect(d_boost.pin("A_2"))
    _net(d, "COMP_5V_RAW").connect(d_boost.pin("K"))
    cap_to_gnd(d, "COMP_5V_RAW", "47uF",  ref="C_BOOST_OUT1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V_RAW", "10uF",  ref="C_BOOST_OUT2", board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V_RAW", "100nF", ref="C_BOOST_OUT3",
               embedded_cap_absorbs=True, board_tag=BTAG)
    # VOUT = 1.229 × (1 + 309/100) = 5.03 V (TPS61175 V_REF, DS §6.5)
    res_between(d, "COMP_5V_RAW", "COMP_5V_FB", "309k",
                ref="R_BOOST_R1", board_tag=BTAG)
    res_between(d, "COMP_5V_FB", "GND",        "100k",
                ref="R_BOOST_R2", board_tag=BTAG)
    # Loop compensation re-derived for THIS point (DS §8.2.2.10; Gea≈330 µS,
    # Rsense 40 mΩ): fRHPZ = RO/(2πL)·(VIN/VOUT)² ≈ 14–20 kHz at 2 A →
    # fC ≈ 4 kHz (≤ fRHPZ/3); |Gps(fC)| ≈ 8 with COUT_eff ≈ 70 µF →
    # R3 = 1/(|Gps|·Gea·R2/(R1+R2)) ≈ 1.6 k; C4 from fZ = fC/10 ≈ 450 Hz
    # → 220 nF. (The 51 k/1.1 nF pair was the 61085's gm/sense design.)
    res_between(d, "COMP_5V_COMP", "COMP_5V_COMP_C", "1.6k",
                ref="R_BOOST_COMP", board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V_COMP_C", "220nF",
               ref="C_BOOST_COMP", board_tag=BTAG)
    # LC filter: COMP_5V_RAW (fins, noisy) → COMP_5V (PMIC, clean).
    ind_between(d, "COMP_5V_RAW", "COMP_5V", "1uH",
                ref="L_PMIC_FILT", board_tag=BTAG)   # TMS-1R0, Isat 2.7 A (was bogus WE-KI 0402)
    cap_to_gnd(d, "COMP_5V", "10uF", ref="C_PMIC_5V_FILT", board_tag=BTAG)

    # Companion-3V3 LDO (U_COMP_33) REMOVED — the two 3.3 V rails are unified.
    # The companion's 3.3 V loads (MP25 VDD-IO + SPI-NAND) now draw from the
    # single 3V3 rail generated on wakeup_board (MCP1640 boost → LDL112 LDO).
    # Both 3.3 V domains already shared the same system-on enable (off in
    # shelf), so this drops a duplicate boost-tap + LDO without changing
    # sequencing or hold-up. COMP_5V is still produced (TPS61175) for the PMIC.

    # ── add_stpmic2 — STPMIC25APQR multi-rail PMIC ───────────────────
    pmic = add_stpmic25apqr(d, ref="U_PMIC", board_tag=BTAG)

    # Power input — all BUCKnIN + LDOnnIN tied to COMP_5V
    _net(d, "COMP_5V").connect(pmic.pin("VIN"))
    for n in (1, 2, 3, 4, 5, 6, 7):
        _net(d, "COMP_5V").connect(pmic.pin(f"BUCK{n}IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO12IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO3IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO56IN"))
    _net(d, "COMP_5V").connect(pmic.pin("LDO78IN"))

    # Grounds — the buck power returns + analog/LDO grounds (DS14278
    # Table 3: PGND1-7 / AGND / GNDLDO tie to GND even when the rail is
    # unused; only the EP was wired before this pass).
    for n in (1, 2, 3, 4, 5, 6, 7):
        _net(d, "GND").connect(pmic.pin(f"PGND{n}"))
    _net(d, "GND").connect(pmic.pin("AGND"))
    _net(d, "GND").connect(pmic.pin("GNDLDO"))

    # VIO — IO-ring reference for SCL/SDA/RSTn/INTn/PWRCTRLx (DS spec
    # 1.7-3.6 V). Tied to the always-on 3V3 bootstrap rail: it matches
    # the I2C2 bus pull-ups (RPU_I2C2_*) and keeps WAKEUPn/RSTn (whose
    # internal pull-ups reference VIO) alive while the PMIC's own COMP
    # rails are down — a PMIC-generated VIO could never be woken.
    _net(d, "3V3").connect(pmic.pin("VIO"))
    # VBUS + VREFDDR stay floating per DS Table 3 "not used" column
    # (USB power-source detect unused; DDR4 VREFCA comes from the
    # discrete R_DDR_VREFCA_TOP/BOT divider, VrefDQ is on-die).

    # Active BUCKs
    _net(d, "PMIC_SW1") .connect(pmic.pin("VLX1"))
    _net(d, "COMP_0V9") .connect(pmic.pin("VOUT1"))
    _net(d, "PMIC_SW3").connect(pmic.pin("VLX3"))
    # BUCK3 retuned 1.35 V → 2.5 V for the DDR4 VPP rail (DDR3L 1.35 V dropped)
    _net(d, "COMP_VPP").connect(pmic.pin("VOUT3"))
    _net(d, "PMIC_SW4") .connect(pmic.pin("VLX4"))
    _net(d, "COMP_1V8") .connect(pmic.pin("VOUT4"))
    _net(d, "PMIC_SW6") .connect(pmic.pin("VLX6"))
    _net(d, "COMP_1V2") .connect(pmic.pin("VOUT6"))
    # BUCK2 → COMP_3V3: the MP25 IO rail, now made by the PMIC so the compute
    # tile boots from COMP_5V alone (depot USB-VBUS) without the wakeup bootstrap
    # 3V3. (The wakeup 3V3 now powers only the WBA/NFC shelf-wake.)
    _net(d, "PMIC_SW2") .connect(pmic.pin("VLX2"))
    _net(d, "COMP_3V3") .connect(pmic.pin("VOUT2"))
    ind_between(d, "PMIC_SW2", "COMP_3V3", "2.2uH",
                ref="L_PMIC_BUCK2", board_tag=BTAG)   # ST Table 2: 2.2 µH for the ≥1.8 V rails
    cap_to_gnd(d, "COMP_3V3", "22uF",  ref="C_PMIC_3V3_1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_3V3", "100nF", ref="C_PMIC_3V3_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # BUCK5 → COMP_0V82: the MP25 VDDCORE domain (DS14284 ROC 0.79–0.842 V
    # — required to START, and the 0.9 V CPU rail is out of its range, so
    # the core gets its own buck; ST's own reference map uses a dedicated
    # 0.82 V buck for VDDCORE). ⚠ NVM: STPMIC25A's BUCK5 default is 1.8 V
    # rank 3 — the bench-provisioning pass that already retunes BUCK2/3/4/6
    # MUST also set BUCK5 = 0.82 V with rank ≤ VDDCPU's (VDD before
    # VDDCORE is enforced by VIN sequencing; see DS14278 Table 1 note).
    _net(d, "PMIC_SW5")  .connect(pmic.pin("VLX5"))
    _net(d, "COMP_0V82") .connect(pmic.pin("VOUT5"))
    # feature="bottom": the 4×4 mm inductor's spacer-clearance cavity on
    # the top face ate enough of the saturated power↔companion joint that
    # WBA nets fell off the lands — the wakeup-facing bottom joint has slack.
    ind_between(d, "PMIC_SW5", "COMP_0V82", "1uH",
                ref="L_PMIC_BUCK5", board_tag=BTAG, feature="bottom")
    cap_to_gnd(d, "COMP_0V82", "22uF",  ref="C_PMIC_0V82_1", board_tag=BTAG,
               feature="bottom")
    cap_to_gnd(d, "COMP_0V82", "100nF", ref="C_PMIC_0V82_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # Unused BUCK 7 — VLX + VOUT decoupling caps on auto-named nets
    for n in (7,):
        vlx_net  = f"PMIC_VLX{n}_TERM"
        vout_net = f"PMIC_VOUT{n}_TERM"
        _net(d, vlx_net) .connect(pmic.pin(f"VLX{n}"))
        _net(d, vout_net).connect(pmic.pin(f"VOUT{n}"))
        cap_to_gnd(d, vlx_net,  "100nF", ref=f"C_PMIC_VLX{n}",  board_tag=BTAG)
        cap_to_gnd(d, vout_net, "100nF", ref=f"C_PMIC_VOUT{n}", board_tag=BTAG)

    # LDO5 → COMP_2V8 (camera analog rail)
    _net(d, "COMP_2V8").connect(pmic.pin("LDO5OUT"))

    # Remaining LDOs (1-2, 4, 6-8) — decoupling caps on auto-named nets
    for n in (1, 2, 4, 6, 7, 8):
        ldo_net = f"PMIC_LDO{n}_TERM"
        _net(d, ldo_net).connect(pmic.pin(f"LDO{n}OUT"))
        cap_to_gnd(d, ldo_net, "100nF", ref=f"C_PMIC_LDO{n}",
                   embedded_cap_absorbs=True, board_tag=BTAG)
    # LDO3 (the DDR sink-source terminator) is unused — DS Table 3 says
    # tie BOTH LDO3IN and LDO3OUT to VIN when not used (no output cap).
    _net(d, "COMP_5V").connect(pmic.pin("LDO3OUT"))

    # Control — I²C on the system I2C2 bus (MP25 PB5/PB4; the TMP117 on
    # this tile already rides it, pull-ups RPU_I2C2_* to 3V3 live on
    # wakeup_board). Without I²C the STPMIC25A NVM defaults are WRONG
    # for this design (BUCK2 def 0.82 V feeds COMP_3V3, BUCK4 def 3.3 V
    # feeds COMP_1V8, BUCK3/6 + LDO5 default OFF), so the M33 must be
    # able to (re)program the rail map.
    _net(d, "I2C2_SCL")    .connect(pmic.pin("SCL"))
    _net(d, "I2C2_SDA")    .connect(pmic.pin("SDA"))
    _net(d, "PMIC_NRST")   .connect(pmic.pin("RSTN"))
    _net(d, "PMIC_PWR_OK") .connect(pmic.pin("INTN"))

    # PONKEY/WAKEUP pull-ups — to the always-on 3V3 (= VIO rail), NOT
    # COMP_5V: WAKEUPn/RSTn/INTn are rated -0.5..+4.2 V abs max (DS14278
    # Table 4), so a 5 V pull-up violates the rating. (They also carry
    # internal pull-ups referenced to VIO/VINTLDO — the externals are
    # belt-and-braces only.)
    _net(d, "PMIC_PONKEY") .connect(pmic.pin("PONKEYN"))
    res_between(d, "3V3", "PMIC_PONKEY", "10k",
                ref="R_PMIC_PONKEY", board_tag=BTAG)
    _net(d, "PMIC_WAKEUP") .connect(pmic.pin("WAKEUPN"))
    res_between(d, "3V3", "PMIC_WAKEUP", "10k",
                ref="R_PMIC_WAKEUP", board_tag=BTAG)

    # PWRCTRL pull-downs (safe-default off)
    _net(d, "PMIC_PWRCTRL1").connect(pmic.pin("PWRCTRL1"))
    _net(d, "PMIC_PWRCTRL2").connect(pmic.pin("PWRCTRL2"))
    _net(d, "PMIC_PWRCTRL3").connect(pmic.pin("PWRCTRL3"))
    res_between(d, "PMIC_PWRCTRL1", "GND", "10k",
                ref="R_PMIC_PWRCTRL1_PD", board_tag=BTAG)
    res_between(d, "PMIC_PWRCTRL2", "GND", "10k",
                ref="R_PMIC_PWRCTRL2_PD", board_tag=BTAG)
    res_between(d, "PMIC_PWRCTRL3", "GND", "10k",
                ref="R_PMIC_PWRCTRL3_PD", board_tag=BTAG)

    # INTLDO bypass — 4.7 µF per DS14278 Table 3 (pin 8) / Table 2 CINTLDO
    _net(d, "PMIC_INTLDO").connect(pmic.pin("INTLDO"))
    cap_to_gnd(d, "PMIC_INTLDO", "4.7uF",
               ref="C_PMIC_INTLDO", board_tag=BTAG)

    # Exposed pad
    _net(d, "GND").connect(pmic.pin("EP"))

    # Buck inductors (1µH, 3A shielded — STPMIC2 reference design)
    # Low-V rails (BUCK1/5/6): ST Table 2 says 0.68 µH; the TMS family has
    # no 0.68 — 1.0 µH is the nearest value on the lower-ripple side
    # (Isat 2.7 A), benign for the adaptive-COT loop (internal ramp).
    ind_between(d, "PMIC_SW1", "COMP_0V9",  "1uH",
                ref="L_PMIC_BUCK1", board_tag=BTAG)
    ind_between(d, "PMIC_SW3", "COMP_VPP",  "2.2uH",
                ref="L_PMIC_BUCK3", board_tag=BTAG)   # ST Table 2
    ind_between(d, "PMIC_SW4", "COMP_1V8",  "2.2uH",
                ref="L_PMIC_BUCK4", board_tag=BTAG)   # ST Table 2
    ind_between(d, "PMIC_SW6", "COMP_1V2",  "1uH",
                ref="L_PMIC_BUCK6", board_tag=BTAG)

    # Per-rail output decoupling
    # Output capacitance: ST Table 2 runs 3-4×22 µF X5R per rail at EVB
    # currents. Here each rail keeps 1×22 µF + the ECM 100 nF: DELIBERATE
    # deviation, justified by (a) rail loads far below the EVB's (no
    # display, NPU at the 0.82 V point), (b) the load-side bulk already
    # on companion (C_MPU_*, C_DDR_BULK*), and (c) the power↔companion
    # LGA joint being SATURATED — adding four more tantalum bodies on
    # this tile threw 21 nets off the lands when tried (2026-06-10).
    cap_to_gnd(d, "COMP_0V9",  "22uF",  ref="C_PMIC_0V9_1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_0V9",  "100nF", ref="C_PMIC_0V9_2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_VPP",  "22uF",  ref="C_PMIC_VPP_1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_VPP",  "100nF", ref="C_PMIC_VPP_2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V8",  "22uF",  ref="C_PMIC_1V8_1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V8",  "100nF", ref="C_PMIC_1V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2",  "10uF",  ref="C_PMIC_1V2_1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2",  "100nF", ref="C_PMIC_1V2_2",
               embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "COMP_2V8",  "4.7uF", ref="C_PMIC_2V8_1", board_tag=BTAG)
    cap_to_gnd(d, "COMP_2V8",  "100nF", ref="C_PMIC_2V8_2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # COMP_5V VIN bulk + distributed per-input locals (ST Table 2 wants
    # 10 µF ceramic per BUCKxIN; 4×2.2 µF 0603 spread along the input pins
    # + the shared bulk approximates it at our lower input ripple)
    cap_to_gnd(d, "COMP_5V", "22uF",  ref="C_PMIC_VIN1", board_tag=BTAG)
    for _i in range(3, 7):
        cap_to_gnd(d, "COMP_5V", "2.2uF", ref=f"C_PMIC_VIN{_i}", board_tag=BTAG)
    cap_to_gnd(d, "COMP_5V", "100nF", ref="C_PMIC_VIN2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # Reset + PWR_OK open-drain pull-ups — to 3V3 (= VIO rail), not
    # COMP_5V: RSTn/INTn abs max is +4.2 V (DS14278 Table 4).
    # Rule-sweep: 3V3 (not COMP_3V3) is LOAD-BEARING for RSTn/PONKEY/
    # WAKEUP — COMP_3V3 is BUCK2's own output, pulling reset to it is a
    # chicken-and-egg lockup. INTN's MP25 reader sees the F5 boot
    # transient (note at the I2C2/3 pull-ups).
    res_between(d, "3V3", "PMIC_NRST",   "10k",
                ref="R_PMIC_NRST",   board_tag=BTAG)
    res_between(d, "3V3", "PMIC_PWR_OK", "10k",
                ref="R_PMIC_PWR_OK", board_tag=BTAG)

    # ── add_optional_camera_ldos — DNP'd LP5907 ×2 for camera rails ──
    ldo_vdd = add_lp5907mfx_1_2_nopb(d, ref="U_CAM_LDO_VDD",
                                      board_tag=BTAG)
    _net(d, "COMP_5V") .connect(ldo_vdd.pin("1"))   # IN
    _net(d, "GND")     .connect(ldo_vdd.pin("2"))   # GND
    _net(d, "COMP_5V") .connect(ldo_vdd.pin("3"))   # EN tied IN
    _net(d, "COMP_1V2").connect(ldo_vdd.pin("5"))   # OUT
    ldo_vdd.dnp = True
    cap_to_gnd(d, "COMP_5V",  "1uF",   ref="C_CAM_LDO_VDD_IN",  board_tag=BTAG)
    cap_to_gnd(d, "COMP_1V2", "2.2uF", ref="C_CAM_LDO_VDD_OUT", board_tag=BTAG)

    ldo_vaa = add_lp5907mfx_2_8_nopb(d, ref="U_CAM_LDO_VAA",
                                      board_tag=BTAG)
    _net(d, "COMP_5V") .connect(ldo_vaa.pin("1"))
    _net(d, "GND")     .connect(ldo_vaa.pin("2"))
    _net(d, "COMP_5V") .connect(ldo_vaa.pin("3"))
    _net(d, "COMP_2V8").connect(ldo_vaa.pin("5"))
    ldo_vaa.dnp = True
    cap_to_gnd(d, "COMP_5V",  "1uF",   ref="C_CAM_LDO_VAA_IN",  board_tag=BTAG)
    cap_to_gnd(d, "COMP_2V8", "4.7uF", ref="C_CAM_LDO_VAA_OUT", board_tag=BTAG)

    # ── add_tmp117(1, I2C2_SCL, I2C2_SDA) ────────────────────────────
    tmp = add_tmp117maidrvr(d, ref="U_TMP1", board_tag=BTAG)
    _net(d, "I2C2_SCL")  .connect(tmp.pin("SCL"))
    _net(d, "I2C2_SDA")  .connect(tmp.pin("SDA"))
    _net(d, "3V3")       .connect(tmp.pin("V+"))
    _net(d, "GND")       .connect(tmp.pin("GND"))
    _net(d, "GND")       .connect(tmp.pin("ADD0"))  # → I²C addr 0x48
    _net(d, "TMP1_ALERT").connect(tmp.pin("ALERT"))
    # TMP117 DS pin table: ALERT is open-drain and "requires a pullup
    # resistor". COMP_3V3 = the reading MP25's IO domain (same rationale
    # as the eFuse PGOOD/FLT pull-ups); the pin is 5.5 V-tolerant.
    res_between(d, "COMP_3V3", "TMP1_ALERT", "10k",
                ref="R_TMP1_ALERT_PU", board_tag=BTAG)
    _net(d, "GND")       .connect(tmp.pin("EP"))    # WSON-6 thermal pad → GND
    cap_to_gnd(d, "3V3", "100nF", ref="C_TMP1",
               embedded_cap_absorbs=True, board_tag=BTAG)
    # NB: system.py's TMP117 placeholder doesn't expose EP. The smash
    # factory does — leave unconnected to match.

    # ── Depot-USB power OR + wake interlock (moved here from
    # build_nose_cap 2026-08-28: these are power_board parts — "the OR
    # diode + its VBUS bulk cap live on POWER_BOARD (where BAT_PROT
    # exists)" — and the shared power tile must fab identically in every
    # config, USB depot present or not). USB 5 V VBUS ORed into BAT_PROT —
    # the protected battery rail that feeds EVERYTHING, so the depot USB-C
    # runs the FULL unit. In configs without the nose USB connector
    # USB_VBUS is a stub net — the parts still fab (shared bare board).
    #
    # Q_USB_OR — IDEAL-DIODE OR (replaced the MBRS540T3G Schottky
    # D_USB_PWR 2026-09-02). The Schottky was a SHELF-LEAKAGE fault, not
    # merely an oversized package: BAT_PROT sits at cell − 0.7 V through
    # Q_ISO's body diode in shelf (power_states.md), so the OR device is
    # reverse-biased across ~3 V for the whole storage life with its anode
    # tied to ground by the wake divider. MBRS540T3G Fig 3 (typical)
    # reads ~3 µA at 3 V / 25 °C, doubling every ~9 °C — against a ~1 µA
    # TOTAL shelf budget, i.e. >the whole pack over the 15 y claim, and
    # enough return current through R_USBWK_G/R_USBWK_PD to walk
    # USBWK_GATE up to a BSS138 threshold and self-wake a warm round.
    # Schottky low-V_F and high I_R are the same physics; a silicon PN
    # diode fixes the leak but its ~0.8 V drop puts BAT_PROT BELOW the
    # cells at the low end of USB tolerance, which breaks the isolation.
    #
    # So: the same P-FET ideal-diode idiom as Q_ISO, one net away, with
    # BAT_PROT as the shared source — Q_ISO's drains face the cell,
    # Q_USB_OR's face VBUS, a textbook 2-input ideal-diode OR. Body diode
    # (drain=USB_VBUS → source=BAT_PROT) passes VBUS FORWARD and blocks
    # BAT_PROT→VBUS, so the dead-USB backfeed the Schottky blocked is
    # still blocked with the gate drive unpowered. OFF-state leak is
    # DMP6110 I_DSS (~nA, −1 µA max) instead of Schottky junction leak.
    # Drop at a ~0.5 A depot load is 130 mΩ ≈ 65 mV (was ~400 mV), so
    # BAT_PROT ≈ 4.94 V against ~4 V cells — the reverse-bias margin that
    # keeps Q_ISO's body diode off GROWS from ~0.35 V to ~0.94 V.
    # Purely hardware: firmware is not in this path at all.
    #
    # BOTTOM (wakeup-facing) face, as the SMC was: the saturated top face
    # has no room — same offload as L_BOOST_COMP.
    # NOTE: like Q_ISO, the forward drop and the gate-drive timing want
    # bench confirmation before fab (analog behaviour, not modelled by
    # the connectivity build).
    q_usb_or = add_dmp6110svt_7(d, ref="Q_USB_OR", feature="bottom",
                                board_tag=BTAG)
    for dp in ("D_1", "D_2", "D_3", "D_4"):
        _net(d, "USB_VBUS").connect(q_usb_or.pin(dp))   # drains → VBUS side
    _net(d, "BAT_PROT")   .connect(q_usb_or.pin("S"))   # source → load side
    _net(d, "USB_OR_G")   .connect(q_usb_or.pin("G"))
    # Gate divider, mirroring Q_ISO: BAT_PROT ─100k─ G ─10k─ DRV drain.
    # DRV off → G≈BAT_PROT (V_GS≈0, OFF, nanopower, body-diode-only).
    # DRV on → G≈BAT_PROT·10/110 ≈ 0.45 V → V_GS≈-4.5 V (fully enhanced,
    # R_DS(on) 130 mΩ, inside the ±20 V V_GSS). The 110k chain draws
    # ~45 µA ONLY while USB is live — i.e. off the depot supply, never
    # off the cells.
    res_between(d, "BAT_PROT",  "USB_OR_G",  "100k", ref="R_USBOR_H", board_tag=BTAG)
    res_between(d, "USB_OR_G",  "USB_OR_GD", "10k",  ref="R_USBOR_L", board_tag=BTAG)
    q_usbor_drv = add_bss138lt1g(d, ref="Q_USBOR_DRV", board_tag=BTAG,
                                 feature="bottom")
    _net(d, "USB_OR_GD").connect(q_usbor_drv.pin("3"))   # drain → gate divider
    _net(d, "GND")      .connect(q_usbor_drv.pin("2"))   # source
    _net(d, "USB_OR_EN").connect(q_usbor_drv.pin("1"))   # gate ← VBUS presence
    # VBUS-presence divider (same idiom as R_ISO_USB_H/L on the interlock):
    # VBUS 5 V → USB_OR_EN 2.5 V, well above the BSS138 V_GS(th) 0.8-1.5 V;
    # VBUS absent → 0 V through R_USBOR_USB_L, so the P-FET defaults OFF.
    res_between(d, "USB_VBUS",   "USB_OR_EN", "100k", ref="R_USBOR_USB_H", board_tag=BTAG)
    res_between(d, "USB_OR_EN",  "GND",       "100k", ref="R_USBOR_USB_L", board_tag=BTAG)
    cap_to_gnd(d, "USB_VBUS", "10uF", ref="C_USB_VBUS",
               feature="bottom", board_tag=BTAG)

    # ── Depot-USB WAKE: VBUS presence joins the MAIN_SW_GATE open-drain
    # OR (4th member after the NFC GPO diode, QHOLD/MP25, QHOLD2/WBA) —
    # plugging the depot cable powers the round up DELIBERATELY (not via
    # the marginal V_GS the diode-OR would otherwise produce). The load
    # then runs ENTIRELY from USB: VBUS−0.4 ≈ 4.7 V on BAT_PROT sits
    # above the 4 V cells, so Q_ISO (force-OFF by the USB interlock, body
    # diode reverse-biased) keeps the pack at zero load-current — only the
    # 3V3_AON trinkets draw from the cells during a depot session (no eFuse
    # IQ any more). Unplug: VBUS falls → Q_USB_WAKE and the Q_ISO interlock
    # release; if no firmware hold is up the round drops cleanly back to
    # shelf, else Q_ISO's body diode hands the load back to the cells.
    q_usbwk = add_bss138lt1g(d, ref="Q_USB_WAKE", board_tag=BTAG,
                          feature="bottom")  # keep the saturated companion joint face clear
    _net(d, "MAIN_SW_GATE").connect(q_usbwk.pin("3"))   # Drain → the latch OR
    _net(d, "GND")         .connect(q_usbwk.pin("2"))   # Source
    _net(d, "USBWK_GATE")  .connect(q_usbwk.pin("1"))   # Gate ← VBUS divider
    res_between(d, "USB_VBUS",   "USBWK_GATE", "10k",
                ref="R_USBWK_G",  board_tag=BTAG)
    res_between(d, "USBWK_GATE", "GND",        "100k",
                ref="R_USBWK_PD", board_tag=BTAG)

    # P_AFT_LGA removed: activation_interface is now flex-connected to
    # power_board (snake), so the rigid-mate LGA harness no longer
    # exists.


def build_wakeup_board(d: Design) -> None:
    """Always-on wakeup tile (post-WLE5 architecture. The 2026-07-30
    crowding split moved the FIN ACTUATION one tile aft onto
    fin_ble_board; the WBA55 cluster briefly went with it and came BACK
    2026-07-31 — the power_states.md ladder is WBA-orchestrated end to
    end, and at the time core_radar dropped fin_ble_board (it no longer
    does — the tile is the battery ceiling + piezo host now), so
    everything wake/activation_unlock-critical was consolidated here and stays):

      • QMAIN/QHOLD/QHOLD2 load-switch + hold latches + MCP1640 boost +
        LDL112PV33R LDO power chain (3V3 always-on rail)
      • STM32WBA55HGF6TR (WLCSP41) — wake orchestrator + BLE 2.4 GHz
        radio, with its DSC1001 MEMS HSE, reset/BOOT0 network, π-match
        + Wilkinson/90°-hybrid RF chain (the Yagi A/B leaves branch off
        THIS tile's N/S edges), the IR_WAKE bias/filter pair and
        RHOLD_AON beside it. In core_radar the Yagi leaves are dropped
        (RF-dark: no BLE session) but the wake/activation_unlock ladder is intact —
        the IR link runs off the radar tile's optics.
      • Wake listeners: RR123 TMR shelf ear + its TPS7A02 nano-LDO,
        DRV5032FC magnetic activation_unlock Hall (MAG_WAKE_N → WBA PC14,
        tile-local), jumpstart wake OR legs (pads on aft_end_board)
      • H3LIS331DL ±400g accelerometer — on the MAIN 3V3 rail +
        M33 I2C3/PD10 (launch witness only; board_tag=activation)
      • 3× test points
      • IIS2MDC magnetometer + 3× ISM330DHCX IMU on I2C2/3 — the flight sensor
        cluster, folded in from the merged-away flight_board (each aft tile had
        only a handful of chips left after flight control moved onto the MP25
        M33). Built via build_flight_board(board_tag="wakeup_board"); their
        INT/DRDY/I2C nets are now local to this tile instead of crossing a gap.

    Removed:
      G0B1 + TCAN1042 CAN-FD bridge — WBA55 (no FDCAN) needed a whole bridge
      MCU + transceiver to reach the CAN bus; with CAN gone it talks to the
      MP25 M33 root directly over LPUART1, so the bridge and the AON_GATED switch
      that gated it are both deleted. Prior WLE5-era: WLE5 + its nano-LDO /
      LSE / RF-match / recovery straps, MT29F NAND, BGS12 LoRa diversity
      switch. NFC subsystem deleted 2026-07-30 (tag + coil + GPO legs)."""
    BTAG = "wakeup_board"

    # ── add_power_input_with_rf_wake — QMAIN load switch + QHOLD latch ──
    qmain = add_irlml6402trpbf(d, ref="QMAIN", board_tag=BTAG)
    _net(d, "BAT_PROT")     .connect(qmain.pin("2"))   # Source
    _net(d, "REG_IN_MAIN")  .connect(qmain.pin("3"))   # Drain
    _net(d, "MAIN_SW_GATE") .connect(qmain.pin("1"))   # Gate

    # Gate pull-up on BAT_RAW (the always-live cell rail): holds QMAIN
    # off in shelf. With the eFuse gone, BAT_PROT is now ALIVE in shelf
    # through Q_ISO's body diode (≈ cell − 0.7 V), so the NFC GPO pull-up
    # to BAT_PROT still works and QMAIN gates REG_IN_MAIN directly — no
    # eFuse-enable step. Depot-USB plug-in wakes the round EXPLICITLY via
    # Q_USB_WAKE (power_board), which joins this gate's open-drain OR.
    res_between(d, "BAT_RAW", "MAIN_SW_GATE", "1M",
                ref="RMAIN_PU",     board_tag=BTAG)
    cap_to_gnd(d, "MAIN_SW_GATE", "100nF", ref="CMAIN_HOLD", board_tag=BTAG)

    # (Q_EFEN removed with the eFuse — there is no longer an eFuse EN to
    # gate. The wake now self-sequences through Q_ISO's body diode:
    # MAIN_SW_GATE low → QMAIN conducts → REG_IN_MAIN rises off the
    # already-live BAT_PROT. Every hold — NFC GPO diode, QHOLD/MP25,
    # QHOLD2/WBA — gates QMAIN alone now.)

    qhold = add_bss138lt1g(d, ref="QHOLD", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE") .connect(qhold.pin("3"))   # Drain
    _net(d, "GND")          .connect(qhold.pin("2"))   # Source
    _net(d, "QHOLD_GATE")   .connect(qhold.pin("1"))   # Gate

    # PWR_HOLD ← the MP25 M33 (inter-board)
    res_between(d, "PWR_HOLD",   "QHOLD_GATE", "100",
                ref="RHOLD_G",      board_tag=BTAG)
    res_between(d, "QHOLD_GATE", "GND",        "100k",
                ref="RHOLD_PD",     board_tag=BTAG)

    # ── GENUINE always-on wake path: NFC tap → QMAIN, no MCU alive ───
    # In TRUE shelf (QMAIN off) every rail aft of REG_IN_MAIN is dead —
    # including the WBA the old design expected to hear the NFC GPO.
    # The ST25DV is the one listener needing NO supply: RF-POWERED, it
    # pulses its open-drain GPO against the existing 330 k pull-up to
    # BAT_PROT (DS13519 Fig. 8: "power-up by RF, no VCC, pull-up on
    # GPO"). One Schottky ORs that pulse onto QMAIN's gate:
    #   tap → GPO low → gate ≈ V_OL + V_f + I·R ≈ 0.7 V → V_GS ≈ −3.3 V
    #   → QMAIN ON → 3V3 rises → WBA boots (ms) and takes the hold over
    # via WBA_WAKE/PB4 long before the wand leaves the field (the
    # CMAIN_HOLD 100 nF × 1 MΩ bridges ~100 ms of handover regardless).
    # Releasing the hold drops back to shelf — Standby→Shelf without activation_unlock
    # still works; with the gate held low the diode just blocks while
    # GPO floats back to BAT_PROT for clean WBA PA8 edges (reverse
    # ≤ ~5 V « 40 V V_R). The 3.3 k series R caps the CMAIN_HOLD
    # discharge at ~1.0 mA — under the GPO's 1.5 mA DC sink abs-max.
    # ⚠ Provisioning: the ST25DV GPO_CTRL NVM bits must enable an RF
    # event (FIELD_CHANGE / RF_USER) so GPO activates with VCC absent; and
    # verify GPO V_OL at 1 mA in RF-only mode at bring-up.
    # ── MAGNETIC activation_unlock listener (repositioned 2026-07-30, same day as
    # the NFC removal): U_MAG_WAKE — a DRV5032FC nanopower Hall (1.6 µA
    # typ, omnipolar so orientation doesn't matter, open-drain) — now on
    # **3V3_AON**, NOT the always-live rail: it hears nothing in TRUE
    # shelf and costs the shelf budget NOTHING (Shelf back to ~1 µA
    # electronic ≈ 15 y). From STANDBY it is the second activation_unlock trigger
    # beside the IR wand: a coded ~2 Hz ≥4.8 mT field (coil or wand
    # magnet — reaches through container/bore walls that block IR;
    # aluminium near-lossless, steel ~30-100× shunted) lands on WBA PC14
    # as an EXTI; the WBA verifies the pattern in a persistence window
    # (mirror of the IR activation_unlock) and then runs the SAME deliberate activation_unlock
    # sequence. NO power-OR legs: activation_unlock is WBA-orchestrated, never a
    # hardware power-pull, and fails CLOSED (no pattern → no activation_unlock). Shelf
    # wake is jumpstart/USB only.
    hall = add_drv5032fcqdbzr(d, ref="U_MAG_WAKE", board_tag=BTAG)
    _net(d, "3V3_AON")   .connect(hall.pin("VCC"))   # activation_unlock listener: alive from Standby, silent+free in Shelf
    _net(d, "GND")       .connect(hall.pin("GND"))
    _net(d, "MAG_WAKE_N").connect(hall.pin("OUT"))
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_MAG_WAKE", board_tag=BTAG)
    # Open-drain node bias: 1 M to 3V3_AON keeps the WBA pin ≤3.3 V (no
    # BAT_RAW level issue). In TRUE shelf AON is down and the node floats
    # — harmless: the shelf wake path needs only the Hall's active sink
    # through the diode, and the WBA is unpowered anyway.
    res_between(d, "3V3_AON", "MAG_WAKE_N", "1M",
                ref="RPU_MAG_WAKE", board_tag=BTAG)

    # ── MAGNETIC SHELF-WAKE ear (2026-07-30, completing the split roles):
    # U_MAG_SHELF — Coto RR123-1H02-612 TMR (20 nA avg, omnipolar,
    # ACTIVE-LOW push-pull, B_OP 0.7 mT — 7× more sensitive than the
    # activation_unlock Hall, so the through-container coil shrinks 7× and
    # through-steel becomes plausible). Its VDD abs-max is 3.6 V so it
    # CANNOT hang on BAT_RAW: a dedicated always-on TPS7A02 (25 nA IQ,
    # EN tied to IN) feeds TMR_VDD → listener total ≈ 45 nA — Shelf stays
    # ~1 µA-class (~15 y). The active-low output drives the SPARE K_2
    # legs of BOTH wake diodes (twin main+AON ORs — the mandatory
    # two-legs rule) through the usual 3.3 k; idle-HIGH at TMR_VDD keeps
    # the diodes blocked, and no MCU pin is involved (no back-power
    # path). f_SW is 1 Hz typ (±50 % over temp) → the coded shelf-wake
    # sequence is SLOW: bits ≥ ~3 s, full wake ~10-15 s — a depot
    # bulk-wake, not a tap. The WBA (once booted) IDs the wake source by
    # elimination and demands the pattern continue before holding.
    tmr_ldo = add_tps7a0233pdbvr(d, ref="U_TMR_LDO", board_tag=BTAG)
    _net(d, "BAT_RAW").connect(tmr_ldo.pin("IN"))
    _net(d, "BAT_RAW").connect(tmr_ldo.pin("EN"))     # always on
    _net(d, "GND")    .connect(tmr_ldo.pin("GND"))
    _net(d, "TMR_VDD").connect(tmr_ldo.pin("OUT"))
    cap_to_gnd(d, "TMR_VDD", "1uF", ref="C_TMR_LDO", board_tag=BTAG)
    tmr = add_rr123_1h02_612(d, ref="U_MAG_SHELF", board_tag=BTAG)
    _net(d, "TMR_VDD")    .connect(tmr.pin("VDD"))
    _net(d, "GND")        .connect(tmr.pin("GND"))
    _net(d, "MAG_SHELF_N").connect(tmr.pin("DIGITAL_OUT"))
    _net(d, "GND")        .connect(tmr.pin("LATCH_CONTROL"))   # latch inactive (VERIFY polarity)
    cap_to_gnd(d, "TMR_VDD", "100nF", ref="C_MAG_SHELF", board_tag=BTAG)
    res_between(d, "MAG_SHELF_K", "MAG_SHELF_N", "3.3k",
                ref="R_MAG_SHELF", board_tag=BTAG)

    # ── JUMPSTART contacts (2026-07-30): two exposed 1.5 mm pads on the
    # AFT face — bridge them with anything metallic and the round boots.
    # Zero-equipment activation: production first-power-on, depot/EOD
    # probe, field fallback when wand/coil/NFC gear is absent. Same latch
    # pattern as every wake source: the bridge pulls a diode leg of the
    # QMAIN gate OR, QHOLD2 latches within ms, the bridge can lift.
    # Moisture immunity by a STIFF divider: 22 k pull-up + 10 k pad
    # series set the wake threshold at bridge ≤ ~35 kΩ — a coin, clip or
    # probe wakes it; a wet/salt film (≥ ~50-100 kΩ) leaves the node high
    # and the diode reverse-biased. Unbridged the leg draws ZERO (node
    # rests at BAT_RAW → 0 V across pull-up AND diode). The 10 k at the
    # pad is also the ESD barrier; the Schottky isolates the gate node.
    # NOT routed to a WBA pin (node rests above 3.3 V): firmware
    # disambiguates the wake source by elimination — no NFC GPO edge, no
    # PC14 pattern, no VBUS ⇒ jumpstart.
    # Ø2.0 pogo pads, not the Ø1.5 _add_testpoint default: these two are the
    # only pads on this face a user BRIDGES rather than probes, so they match
    # the rest of the bench array's 2.0 mm size (uniform field, one fixture
    # pitch) and give a coin or clip more copper to land on. JUMP_WAKE carries
    # the square group-start silhouette.
    tp_jw = add_pogo_pad(d, ref="TP_JUMP_WAKE", board_tag="aft_end_board",
                         manf_pn=None, square=True)
    tp_jg = add_pogo_pad(d, ref="TP_JUMP_GND", board_tag="aft_end_board",
                         manf_pn=None)
    _net(d, "JUMP_PAD").connect(tp_jw.pin("1"))
    _net(d, "GND")     .connect(tp_jg.pin("1"))
    res_between(d, "JUMP_PAD", "JUMP_WAKE", "10k",
                ref="R_JUMP_PAD", board_tag="aft_end_board")
    res_between(d, "BAT_RAW", "JUMP_WAKE", "22k",
                ref="R_JUMP_PU", board_tag=BTAG)
    d_jump = add_bat64_06_tp(d, ref="D_JUMP_WAKE", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE").connect(d_jump.pin("COM_A"))
    _net(d, "JUMP_WAKE_K") .connect(d_jump.pin("K_1"))
    res_between(d, "JUMP_WAKE_K", "JUMP_WAKE", "3.3k",
                ref="R_JUMP_WAKE", board_tag=BTAG)
    _net(d, "MAG_SHELF_K").connect(d_jump.pin("K_2"))   # TMR shelf-wake leg

    # ── MCP1640 boost regulator (REG_IN_MAIN → BOOST_OUT ≈ 3.87 V) ──
    boost = add_mcp1640ct_i_chy(d, ref="U_BOOST", board_tag=BTAG)
    _net(d, "REG_IN_MAIN") .connect(boost.pin("3"))    # VIN
    _net(d, "GND")         .connect(boost.pin("2"))    # GND
    _net(d, "BOOST_SW")    .connect(boost.pin("1"))    # SW
    _net(d, "BOOST_OUT")   .connect(boost.pin("5"))    # VOUT
    _net(d, "REG_IN_MAIN") .connect(boost.pin("6"))    # EN tied VIN
    _net(d, "BOOST_FB")    .connect(boost.pin("4"))    # FB

    # 2.2 µH TMS (real 0806 power part, Isat 1.2 A » the ~0.2 A boost
    # peaks; MCP1640 DS inductor range 2.2–10 µH). The old binding was a
    # nonexistent "WE-KI 0402 4.7 µH" RF part (family capped ~120 nH) —
    # same bogus binding fixed on L_BOOST_COMP + both AWR bucks.
    ind_between(d, "REG_IN_MAIN", "BOOST_SW", "2.2uH",
                ref="L_PWR", board_tag=BTAG)
    res_between(d, "BOOST_OUT", "BOOST_FB", "220k",
                ref="R_BOOST_FB1", board_tag=BTAG)
    res_between(d, "BOOST_FB",  "GND",      "100k",
                ref="R_BOOST_FB2", board_tag=BTAG)
    cap_to_gnd(d, "REG_IN_MAIN", "10uF",  ref="CBOOST_IN1",  board_tag=BTAG)
    cap_to_gnd(d, "REG_IN_MAIN", "100nF", ref="CBOOST_IN2",  board_tag=BTAG)
    cap_to_gnd(d, "BOOST_OUT",   "22uF",  ref="CBOOST_OUT1", board_tag=BTAG)
    cap_to_gnd(d, "BOOST_OUT",   "100nF", ref="CBOOST_OUT2",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── LDL112PV33R: BOOST_OUT (3.87 V) → 3V3 ──
    # ST DS10321 Table 1: pin 1=EN, pin 2=GND, pin 3=ADJ (NC on fixed),
    # pin 4=VOUT, pin 5=NC, pin 6=VIN, pin 7=EP-to-GND.
    ldo_pwr = add_ldl112pv33r(d, ref="U_PWR", board_tag=BTAG)
    _net(d, "BOOST_OUT") .connect(ldo_pwr.pin("VIN"))
    _net(d, "GND")       .connect(ldo_pwr.pin("GND"))
    _net(d, "BOOST_OUT") .connect(ldo_pwr.pin("EN"))   # tied VIN → always-on
    _net(d, "3V3")       .connect(ldo_pwr.pin("VOUT"))
    _net(d, "GND")       .connect(ldo_pwr.pin("EP"))   # thermal pad → GND
    cap_to_gnd(d, "3V3", "22uF",  ref="COUT1", board_tag=BTAG)
    cap_to_gnd(d, "3V3", "22uF",  ref="COUT2", board_tag=BTAG)
    cap_to_gnd(d, "3V3", "100nF", ref="COUT3",
               embedded_cap_absorbs=True, board_tag=BTAG)

    # ── add_st25dv_tssop8_rf_wake — NFC dual-port tag ──
    # AON latch host tile. Was activation_interface ("beside the ST25DV/H3LIS")
    # — moved to wakeup_board 2026-07-31 in the activation chip redistribution:
    # the ST25DV is deleted, and every other member of the wake pattern (WBA
    # hold, TMR shelf ear, Hall listener, D_JUMP_WAKE, the QHOLD/QMAIN
    # latches) already lives on wakeup_board, so AON_EN / MAG_SHELF_K become
    # tile-local there. (NOT fin_ble_board: core_radar dropped that tile at
    # the time — it no longer does — and the wake pattern is wakeup-local
    # anyway.)
    _ACT_TAG = "wakeup_board"

    # ── NFC subsystem REMOVED 2026-07-30 (user decision): the ST25DV tag,
    # its Ø22 antenna flex, GPO wake legs, session-gated VCC (WBA PA7) and
    # GPO EXTI (WBA PA8) are all deleted. Wake channels are now MAGNETIC
    # (coded field → U_MAG_WAKE Hall), JUMPSTART (aft contact pads) and
    # depot USB; per-round identity/telemetry rides the IR/BLE session
    # post-wake; activation_unlock release = IR wand. Consequence accepted: there is no
    # zero-power Shelf interrogation any more — a shelf round must be
    # woken (magnet/jumpstart, µJ) to be queried.

    # ── 3V3_AON — the nanopower STANDBY domain (TPS7A02, 25 nA IQ) ────
    # Hangs directly on BAT_RAW, UPSTREAM of the wake-gated eFuse: in
    # Standby the eFuse + QMAIN are both OFF and only this domain lives
    # (WBA55 + H3LIS + ST25DV VCC + TLV3691 ≈ 17 µA), so Standby
    # drops from ~320 µA (26 d) to ~28 µA (~10 months on the 1-cell
    # pack). The LDO's own current limit is the protection for this
    # µA-class domain (it bypasses the eFuse by design). Sited on
    # wakeup_board beside the WBA + Hall (two of its loads) and the rest
    # of the wake-latch pattern; BAT_RAW reaches it over the backbone.
    aon = add_tps7a0233pdbvr(d, ref="U_AON_LDO", board_tag=_ACT_TAG)
    _net(d, "BAT_RAW").connect(aon.pin("IN"))
    _net(d, "GND")    .connect(aon.pin("GND"))
    _net(d, "AON_EN") .connect(aon.pin("EN"))    # smart internal pull-down: floats = OFF
    _net(d, "3V3_AON").connect(aon.pin("OUT"))
    cap_to_gnd(d, "BAT_RAW", "1uF", ref="C_AON_IN",  board_tag=_ACT_TAG)
    cap_to_gnd(d, "3V3_AON", "1uF", ref="C_AON_OUT", board_tag=_ACT_TAG)

    # AON-EN latch — third instance of the wake pattern: Q_AON_EN raises
    # EN to BAT_RAW when a wake source (magnetic / jumpstart via
    # D_AON_WAKE's shared cathode nets, since the 2026-07-30 NFC removal)
    # or the depot-USB presence (Q_USB_WAKE2, gate on the shared USBWK divider) pulls
    # its gate low. The WBA then HOLDS AON via PB15 → 1 k → EN (a 3V3-
    # push-pull high; safe vs the FET's 4 V drive through the 1 k, and a
    # DEAD PB15 leaks nothing because EN idles at 0 V in shelf). States:
    #   shelf   = no holds, EN=0     → AON + main both off (~10 µA)
    #   standby = WBA holds EN only  → AON on, eFuse+QMAIN off (~28 µA)
    #   on      = + PB4/PWR_HOLD     → everything up
    q_aon = add_irlml6402trpbf(d, ref="Q_AON_EN", board_tag=_ACT_TAG)
    _net(d, "BAT_RAW")    .connect(q_aon.pin("2"))   # Source
    _net(d, "AON_EN")     .connect(q_aon.pin("3"))   # Drain → LDO EN
    _net(d, "AON_EN_GATE").connect(q_aon.pin("1"))   # Gate
    res_between(d, "BAT_RAW", "AON_EN_GATE", "1M",
                ref="RAON_PU", board_tag=_ACT_TAG)
    # D_AON_WAKE (was D_NFC_WAKE2): the AON-side wake OR. Shares each
    # source's cathode net with the main-OR diode (the proven two-diode
    # topology NFC used) so a magnetic or jumpstart wake raises BOTH the
    # main rail AND 3V3_AON — without this the WBA (which lives on AON)
    # never boots and the round falls back asleep after the ~100 ms gate
    # hold. (Latent bug in the first mag/jumpstart wiring, found and
    # fixed during the NFC removal 2026-07-30.)
    d_aon = add_bat64_06_tp(d, ref="D_AON_WAKE", board_tag=_ACT_TAG)
    _net(d, "AON_EN_GATE").connect(d_aon.pin("COM_A"))
    _net(d, "JUMP_WAKE_K").connect(d_aon.pin("K_1"))   # shared 3.3 k → JUMP_WAKE
    _net(d, "MAG_SHELF_K").connect(d_aon.pin("K_2"))   # TMR shelf-wake leg (twin-OR rule)
    q_usbwk2 = add_bss138lt1g(d, ref="Q_USB_WAKE2", board_tag=_ACT_TAG)
    _net(d, "AON_EN_GATE").connect(q_usbwk2.pin("3"))  # Drain
    _net(d, "GND")        .connect(q_usbwk2.pin("2"))  # Source
    _net(d, "USBWK_GATE") .connect(q_usbwk2.pin("1"))  # Gate ← shared VBUS divider

    # WLE5 + dedicated nano-LDO + 12-ball bypass network removed.
    # WBA55 replaces the wake orchestrator + 2.4 GHz radio role (added
    # below by task #7); it runs directly from the 3V3 rail (no dedicated
    # LDO needed). MP25 M33 recovery via BLE OTA — no more WLE5↔H562 strap
    # resistors. The wake nets MAG_WAKE_N + IR_WAKE terminate at the WBA55
    # additions below (H3LIS_* moved to the M33 with the IR-wake change);
    # its LPUART1 now goes to the
    # MP25 M33 root (WBA_UART_*) instead of the removed CAN bridge.

    # AON load-switch REMOVED (QAON / QAON_EN PMOS+NMOS + R_AON_PU /
    # R_AON_EN_PD / C_AON1 / C_AON2). It gated the G0B1+TCAN CAN bridge (now
    # deleted) and the H3LIS accel off in shelf; with the bridge gone the only
    # consumer was the µA-class accel, which simply runs from 3V3 now. The
    # AON_EN GPIO on the WBA55 is freed.

    # ── STM32WBA55HGF6TR wake orchestrator + BLE 2.4 GHz radio ─────────
    # Thin WLCSP41 (2.98 × 2.76 mm) — 6× smaller area than the WBA52
    # QFN48 it replaces. Pin allocation against datasheet Table 24
    # (WLCSP41 column) — see DS14127 Rev 10. Consolidated roles:
    #   - Wake orchestrator (RTC + EXTI from MAG_WAKE_N and IR_WAKE)
    #   - Optical service link (2026-07-27): IR_WAKE RX (PA12) + IR_TX
    #     keying (PA6). Standby is
    #     RF-SILENT — no standing BLE advertising; an IR/NFC
    #     interrogation wakes the WBA, which brings BLE up for a
    #     bounded session (IR-initiated BLE), then goes dark again.
    #   - BLE Coded scan + 2 Mbps PHY for in-flight telemetry (UNCHANGED
    #     — the Yagi pair + backward beam keep the flight datalink)
    #   - MAIN_SW_GATE driver (flight-rail PMOS gate)
    #   - SPI3 HCI link to the MP25 application processor (SPI1 unusable
    #     on WLCSP41 because SPI1_MISO is only on PB3 which we need for
    #     I²C1_SDA → ST25DV)
    #   - LPUART1 → MP25 M33 root (firmware bootloader + console — replaces the
    #     old G0B1/CAN bridge; WBA55 has no FDCAN, but UART to the root needs
    #     no transceiver)
    #   - I²C1 → ST25DV (WBA I²C3 freed — H3LIS now on the M33's I2C3)
    # Lives directly on the always-on 3V3 rail (no dedicated nano-LDO).
    # 32 MHz HSE via MEMS resonator (shock-tolerant); LSE = internal LSI
    # which frees PC14/PC15 as plain spare GPIOs.
    # Mandatory: die-area underfill (Hysol FP4549) — captured on the
    # Chip record; an assembly-process validator enforces it.
    wba = add_stm32wba55hgf6tr(d, ref="U_WBA", board_tag=BTAG)

    # Power pins — all VDD variants → 3V3_AON (the nanopower standby
    # domain: the WBA must run in Standby with the eFuse + main path
    # OFF), VSS → GND.
    _net(d, "3V3_AON").connect(wba.pin("VDDA"))      # E12 — analog
    _net(d, "3V3_AON").connect(wba.pin("VDD_ANA"))   # B5  — analog (VDDANA)
    _net(d, "3V3_AON").connect(wba.pin("VDD_1"))     # A10 — digital
    _net(d, "3V3_AON").connect(wba.pin("VDD_2"))     # G4
    _net(d, "3V3_AON").connect(wba.pin("VDDRF"))     # A6  — radio digital
    _net(d, "3V3_AON").connect(wba.pin("VDDRF_PA"))  # C6  — radio PA (needs ≥2.5 V for +9.5 dBm)
    _net(d, "3V3_AON").connect(wba.pin("VDD_HPA"))   # C4  — high-power PA
    _net(d, "GND").connect(wba.pin("VSS_1"))     # B9
    _net(d, "GND").connect(wba.pin("VSS_2"))     # G6
    _net(d, "GND").connect(wba.pin("VSSA"))      # D13
    _net(d, "GND").connect(wba.pin("VSSRF_1"))   # D1
    _net(d, "GND").connect(wba.pin("VSSRF_2"))   # D3
    _net(d, "GND").connect(wba.pin("VSSRF_3"))   # D5

    # SMPS step-down for digital core (cuts Run current by ~30 % vs LDO
    # mode). Reference network from RM0497 §6.10: VDDSMPS = 3V3 input,
    # VLXSMPS through 2.2 µH inductor + 2.2 µF cap → VDD11 (regulated
    # ~1.1 V core supply). VSSSMPS is the low-noise SMPS ground return.
    _net(d, "3V3_AON")        .connect(wba.pin("VDD_SMPS"))   # B13
    _net(d, "GND")        .connect(wba.pin("VSS_SMPS"))   # A12
    _net(d, "WBA_VLX")    .connect(wba.pin("VLX_SMPS"))   # C12
    _net(d, "WBA_VDD11")  .connect(wba.pin("VDD11"))      # B11
    ind_between(d, "WBA_VLX", "WBA_VDD11", "2.2uH",
                ref="L_WBA_SMPS", board_tag=BTAG)
    cap_to_gnd(d, "WBA_VDD11", "2.2uF",
               ref="C_WBA_VDD11", board_tag=BTAG)

    # VDD decoupling — one 100 nF per pin + bulk. The embedded plane
    # absorbs the per-pin caps; the bulk stays discrete for ESR.
    for tag in ("VDDA", "VDDANA", "VDD1", "VDD2", "VDDRF", "VDDRFPA",
                "VDDHPA", "VDDSMPS"):
        cap_to_gnd(d, "3V3_AON", "100nF", ref=f"C_WBA_{tag}",
                   embedded_cap_absorbs=True, board_tag=BTAG)
    cap_to_gnd(d, "3V3_AON", "4.7uF", ref="C_WBA_BULK", board_tag=BTAG)

    # NRST network — 10 kΩ pull-up + 100 nF to GND (RM0497 §6.3.5).
    _net(d, "WBA_NRST").connect(wba.pin("NRST"))   # E2
    res_between(d, "3V3_AON", "WBA_NRST", "10k",
                ref="R_WBA_NRST", board_tag=BTAG)
    cap_to_gnd(d, "WBA_NRST", "100nF",
               ref="C_WBA_NRST", board_tag=BTAG)
    # MP25 → WBA reset, open-drain via NFET (rule-sweep F1 fix): PB3 is
    # a TT pin clamped to VDDIO4/COMP_3V3, so a direct tie onto this
    # 3V3_AON-pulled net back-fed ~280 µA through the dead MP25 every
    # standby second. Gate has no clamp; the 100 k pull-down keeps the
    # FET off while PB3 floats (standby, MP25 POR). FIRMWARE: PB3 HIGH
    # = reset WBA (inverted vs the old direct tie); with WBA_BOOT0
    # (PI10) high first this enters the ROM bootloader for the post-pot
    # reflash over the UART/HCI link (initial load stays SWD-on-pogos).
    # feature="bottom": on the top (power-facing) face the SOT-23 threw
    # WBA_UART_*/WBA_RST_CMD off the tight wakeup↔power lands.
    q_wbarst = add_bss138lt1g(d, ref="Q_WBA_RST", board_tag=BTAG,
                              feature="bottom")
    _net(d, "WBA_NRST")   .connect(q_wbarst.pin("3"))   # Drain
    _net(d, "GND")        .connect(q_wbarst.pin("2"))   # Source
    _net(d, "WBA_RST_CMD").connect(q_wbarst.pin("1"))   # Gate ← MP25 PB3
    res_between(d, "WBA_RST_CMD", "GND", "100k",
                ref="R_WBARST_PD", board_tag=BTAG)

    # BOOT0 — pull-down for normal flash boot. (Recovery uses BLE OTA.)
    _net(d, "WBA_BOOT0").connect(wba.pin("PH3-_BOOT0"))   # C8
    res_between(d, "WBA_BOOT0", "GND", "10k",
                ref="R_WBA_BOOT0", board_tag=BTAG)

    # 32 MHz HSE — MEMS clipped-sine clock into OSC_IN. OSC_OUT NC
    # (HSEBYP=1 in RCC_CR; no crystal feedback path).
    hse_osc = add_dsc1001ci5_032_0000(d, ref="Y_WBA_HSE", board_tag=BTAG)
    _net(d, "3V3_AON")    .connect(hse_osc.pin("1"))  # STANDBY# tied VDD
    _net(d, "GND")        .connect(hse_osc.pin("2"))
    _net(d, "WBA_HSE_IN") .connect(hse_osc.pin("3"))  # OUT
    _net(d, "3V3_AON")    .connect(hse_osc.pin("4"))  # VDD
    _net(d, "WBA_HSE_IN") .connect(wba.pin("OSC_IN"))   # A8
    cap_to_gnd(d, "3V3_AON", "100nF", ref="C_WBA_HSE_VDD",
               embedded_cap_absorbs=True, board_tag=BTAG)
    # LSE = internal LSI (±5 %); PC14/PC15 reused as GPIOs.

    # SWD debug
    _net(d, "WBA_SWDIO").connect(wba.pin("PA13"))  # E8 — JTMS/SWDIO
    _net(d, "WBA_SWCLK").connect(wba.pin("PA14"))  # F1 — JTCK/SWCLK

    # LPUART1 ↔ MP25 M33 UART (firmware bootloader host + console). Was the
    # G0B1/CAN bridge link; now a direct UART to the MP25 M33 root — the
    # bridge MCU + transceiver are gone (WBA55 has no FDCAN, so CAN required a
    # whole bridge; UART to the root needs none). PA2=TX, PA1=RX (Table 24).
    _net(d, "WBA_UART_TX") .connect(wba.pin("PA2"))   # F11 — LPUART1_TX → MP25 M33 RX
    _net(d, "WBA_UART_RX") .connect(wba.pin("PA1"))   # E10 — LPUART1_RX ← MP25 M33 TX

    # I²C1 → ST25DV. PA15=I2C1_SCL, PB3=I2C1_SDA (only SDA option in
    # WLCSP41). The ST25DV block above keeps the legacy I2C2_SCL/SDA
    # net names — wiring stable across the chip swap.
    _net(d, "I2C2_SCL").connect(wba.pin("PA15"))  # F3
    _net(d, "I2C2_SDA").connect(wba.pin("PB3"))   # G2

    # PA6/PA7 (freed by the H3LIS→M33 move) re-tasked for the optical
    # service link (2026-07-27):
    # IR_TX → the D_IR_TX gate on radar_module (3 joints; drive loop is
    # tile-local at the nose — see the radar builder). Bit-banged OOK
    # from Run, or hardware-timer subcarrier if PA6 has a TIM AF on
    # WLCSP41 (check DS14403 at bring-up — not blocking, kbps needs none).
    _net(d, "IR_TX").connect(wba.pin("PA6"))        # D9
    # (ST25DV session-power role deleted with the NFC removal 2026-07-30.)
    # (PA7 freed 2026-07-30 — ST25DV session-VCC gate left with the NFC removal.)

    # SPI3 HCI link to MP25 (SPI1 unusable — see header comment).
    _net(d, "WBA_HCI_SCK") .connect(wba.pin("PA0"))   # G12 — SPI3_SCK
    _net(d, "WBA_HCI_MISO").connect(wba.pin("PB9"))   # F9  — SPI3_MISO
    _net(d, "WBA_HCI_MOSI").connect(wba.pin("PB8"))   # G10 — SPI3_MOSI
    _net(d, "WBA_HCI_NSS") .connect(wba.pin("PA5"))   # F13 — SPI3_NSS
    _net(d, "WBA_HCI_IRQ") .connect(wba.pin("PB12"))  # C10 — host-wake GPIO

    # EXTI wake inputs
    # (PA8/EXTI8 freed 2026-07-30 — the NFC GPO left with the NFC removal.)
    # MAG_WAKE_N ← U_MAG_WAKE DRV5032FC Hall (open-drain, 1 M to 3V3_AON;
    # see the magnetic-wake block). Standby listener for the coded magnetic
    # pattern — any EXTI-capable GPIO wakes the WBA from Stop1, same
    # mechanism as the IR photodiode on EXTI12. PC14 was the freed
    # OSC32 spare (LSE = internal LSI); PC15 remains spare.
    _net(d, "MAG_WAKE_N").connect(wba.pin("PC14-_OSC32__IN"))  # A4 — EXTI wake

    # IR_WAKE ← D_IR_WAKE photodiode cathode on radar_module (see the
    # radar builder for the full rationale). Bias + filter live HERE, next
    # to the WBA: 470 k pull-up to 3V3_AON (the wake threshold), 10 nF to
    # GND (τ ≈ 4.7 ms with the pull-up — EMI/debounce for the 3-joint
    # backbone run past the DDR/radar switching). The cap is a REAL
    # discrete on a private high-Z node — never ECM-absorbed (same rule
    # as the mag's C1 reservoir). EXTI12 is free: PB12 (shared line
    # number) is an output (HCI IRQ to the MP25).
    res_between(d, "3V3_AON", "IR_WAKE", "470k",
                ref="RPU_IR_WAKE", board_tag=BTAG)
    cap_to_gnd(d, "IR_WAKE", "10nF", ref="C_IR_WAKE", board_tag=BTAG)
    _net(d, "IR_WAKE").connect(wba.pin("PA12"))   # E6 — EXTI12, falling edge

    _net(d, "WBA_WAKE").connect(wba.pin("PB4"))   # F5 — GPIO, push high to hold
    # AON hold — PB15 (poetically, the old AON_GATED enable pin) pushes
    # HIGH into the TPS7A02's EN through 1 k: holds the 3V3_AON domain
    # (= the WBA's own life support) after the NFC tap ends. Releasing
    # it (with PB4 already low) drops the round to TRUE shelf.
    _net(d, "WBA_AON_HOLD").connect(wba.pin("PB15"))   # E4 — push high to hold AON
    res_between(d, "WBA_AON_HOLD", "AON_EN", "1k",
                ref="RHOLD_AON", board_tag=BTAG)

    # Antenna pin → π-match → Wilkinson input.
    _net(d, "WBA_RF").connect(wba.pin("RF"))  # C2

    # ── WBA55 RF chain — π-match + Wilkinson + 90° hybrid ───────────
    # Antenna chain: WBA55 RF pin → π-match → Wilkinson 3 dB splitter
    # → 90° branchline hybrid → Yagi-A + Yagi-B feeds. The Wilkinson
    # and the hybrid coupler are distributed-element microstrip
    # structures laid down directly in copper on the wakeup_board RF
    # layer (no lumped components beyond the Wilkinson isolation
    # resistor) — they're not instantiated as parts. Real microstrip
    # widths and lengths pending the antenna-team EM-sim work flagged
    # in the plan's out-of-scope section.
    #
    # The BGS12 SPDT (U_SPDT) that used to sit between the π-match and
    # the Wilkinson is REMOVED along with its ANT_NOSE throw: the nose
    # chip antenna it selected was deleted in the radar forward-end
    # nose-thinning pass (the metal block would detune it), leaving the
    # switch with a single live throw. Short-range BLE (programming /
    # activation_unlock) now rides the Yagi pair; NFC covers activation_unlock/wake
    # independently. Frees WBA PA12 (RF_ANTSW0) + PC15 (SPDT_PWR).

    # π-match L + 2 shunt C between WBA RF pin and the Wilkinson input.
    # Values are placeholders; topology is locked. `feature="rf"` keeps
    # these on the top face (face_split's ECM-embedding rule normally
    # sweeps 0402/0603 passives to the bottom — RF nets need the
    # matching network adjacent to the radio with controlled-impedance
    # microstrip, NOT inside the embedded-cap laminate).
    ind_between(d, "WBA_RF", "WBA_RF_M", "2.7nH",
                ref="L_WBA_PI", board_tag=BTAG, feature="rf")
    cap_to_gnd(d, "WBA_RF",   "0.5pF", ref="C_WBA_PI1",
               board_tag=BTAG, feature="rf")
    cap_to_gnd(d, "WBA_RF_M", "0.5pF", ref="C_WBA_PI2",
               board_tag=BTAG, feature="rf")

    # Wilkinson 3 dB splitter + 90° branchline hybrid (microstrip).
    # The Wilkinson splits WBA_RF_M → YAGI_WILK_A + YAGI_WILK_B
    # (in-phase); the 100 Ω isolation resistor sits across the two
    # output ports. The hybrid then adds a 90° phase offset on one
    # branch on its way to YAGI_RF_A vs YAGI_RF_B → circular pol.
    res_between(d, "YAGI_WILK_A", "YAGI_WILK_B", "100",
                ref="R_WILK_ISO", board_tag=BTAG)
    # Stitch the named nets onto courtesy test points so the canonical
    # netlist sees them and so the routing tools can find the right
    # microstrip endpoints. (The actual splitter/hybrid traces are drawn
    # in copper at routing time, no chip instances here. WBA_RF_M — the
    # Wilkinson input — needs no test point: the π-match parts anchor it.)
    for tp_ref, tp_net in (("TP_WILK_A",   "YAGI_WILK_A"),
                           ("TP_WILK_B",   "YAGI_WILK_B"),
                           ("TP_YAGI_RF_A", "YAGI_RF_A"),
                           ("TP_YAGI_RF_B", "YAGI_RF_B")):
        tp = _add_testpoint(d, ref=tp_ref, board_tag=BTAG)
        _net(d, tp_net).connect(tp.pin("1"))

    # WLE5 LSE oscillator removed — WBA55 uses internal LSI (±5 %); LSE
    # crystal not needed for periodic BLE-scan timing accuracy.

    # WLE5 reset / BOOT0 / RF pi-network / test point all removed.

    # MT29F NAND removed (higher comms speeds eliminate OTA buffering).

    # G0B1 + TCAN1042 CAN bridge REMOVED. It existed only to put the WBA55
    # (which has no FDCAN peripheral) onto the CAN bus — an entire bridge MCU
    # + transceiver. With CAN gone, the WBA55 talks to the MP25 M33 root directly
    # over LPUART1 (firmware + console, wired above) and rides SYS_I2C for
    # runtime telemetry. This deletes U_G0B1 + U_TCAN + their decoupling /
    # reset network, and frees the AON_GATED rail (now only the accel — see
    # the power-simplification pass).

    # BGS12 SP2T LoRa diversity switch removed. Its BGS12 successor (the
    # nose-chip-antenna vs Yagi-pair SPDT off the WBA55 antenna pin) is
    # gone too — see the RF-chain comment above.

    # Flight-rail HOLD — via a dedicated low-side FET (QHOLD2), the same
    # pattern as the MP25's PWR_HOLD/QHOLD. The old bare 10 k from PB4 to
    # MAIN_SW_GATE defeated TRUE shelf: with the WBA unpowered, the gate
    # node (at BAT_PROT through the 1 MΩ pull-up) leaked into the dead
    # PB4 — sub-µA of unpowered-pin leakage × 1 MΩ sags the gate ~1 V,
    # enough to half-enhance QMAIN (V_th(max) −0.95 V). A FET hold has no
    # path when its driver is dead (the 100 k gate pull-down keeps it
    # off). ⚠ FIRMWARE: hold polarity INVERTED vs the old wiring — the
    # WBA now drives PB4 HIGH to hold power (was: low/open-drain-low).
    qhold2 = add_bss138lt1g(d, ref="QHOLD2", board_tag=BTAG)
    _net(d, "MAIN_SW_GATE").connect(qhold2.pin("3"))   # Drain
    _net(d, "GND")         .connect(qhold2.pin("2"))   # Source
    _net(d, "QHOLD2_GATE") .connect(qhold2.pin("1"))   # Gate
    res_between(d, "WBA_WAKE",    "QHOLD2_GATE", "100",
                ref="RHOLD2_G",  board_tag=BTAG)
    res_between(d, "QHOLD2_GATE", "GND",         "100k",
                ref="RHOLD2_PD", board_tag=BTAG)

    # ── add_h3lis_accel — H3LIS331DL ±400g, back on the MAIN 3V3 rail ──
    # Wired per ST datasheet DocID13335 LGA-16 pinout. IR-wake change
    # (2026-07): the accel left the 3V3_AON domain — its Standby
    # motion-detect role (10 µA, the old Standby→staged trigger) is
    # replaced by the D_IR_WAKE photodiode on the radar tile, so it now
    # powers up with the main rail at Ready (the merged staged state) and keeps only its
    # launch-witness + flight-recorder roles (quantitative ±400 g beside
    # the piezo's fast edge; the ±16 g ISM330s saturate at setback).
    # I²C moved WBA→M33 with the rail: it joins the M33's I2C3 bus
    # (addr 0x18 — no clash with IMU2/IMU3 at 0x6A/0x6B; bus pull-ups
    # RPU_I2C3_* to 3V3 already exist on wakeup_board, so the dedicated
    # RPU_HACC_* pair is gone). Unpowered-on-dead-bus is the same
    # pattern as every 3V3 sensor in Standby. INT1 → M33 PD10 EXTI.
    # board_tag=activation_interface: the H3LIS331 ±400g high-G accel is pinned
    # to the activation tile dead-centre (on the spin axis) for clean axial
    # setback sensing; I2C3/INT reach the M33 over the backbone.
    acc = add_h3lis331dltr(d, ref="U_HACC", board_tag="activation_interface")
    _net(d, "3V3")       .connect(acc.pin("VDD_IO"))   # 1
    # 2, 3 = NC_1, NC_2 → leave floating per datasheet
    _net(d, "I2C3_SCL")  .connect(acc.pin("SCL"))      # 4
    _net(d, "GND")       .connect(acc.pin("GND_1"))    # 5
    _net(d, "I2C3_SDA")  .connect(acc.pin("SDA"))      # 6
    _net(d, "GND")       .connect(acc.pin("SDO"))      # 7 SDO/SA0 → addr 0x18
    _net(d, "3V3")       .connect(acc.pin("CS"))       # 8 CS high → I2C mode
    # INT2 (pin 9) is a logic OUTPUT — leave floating per datasheet.
    # Tying to GND would short the driver when firmware enables it.
    # Firmware masks INT2 via INT_CFG register (CTRL_REG3 = 0).
    _net(d, "GND")       .connect(acc.pin("RESERVED_1"))  # 10 — DS9012 Tab 1: connect to GND
    _net(d, "H3LIS_INT1").connect(acc.pin("INT1"))     # 11
    _net(d, "GND")       .connect(acc.pin("GND_2"))    # 12
    _net(d, "GND")       .connect(acc.pin("GND_3"))    # 13
    _net(d, "3V3")       .connect(acc.pin("VDD"))      # 14
    _net(d, "3V3")       .connect(acc.pin("RESERVED_2"))  # 15 — DS9012 Tab 1: connect to Vdd (NOT GND — the two reserved straps differ)
    _net(d, "GND")       .connect(acc.pin("GND_4"))    # 16
    # DS9012 §"Application hints": 100 nF ceramic + 10 µF bulk at pin 14
    cap_to_gnd(d, "3V3", "100nF", ref="C_HACC1",
               embedded_cap_absorbs=True, board_tag="activation_interface")
    cap_to_gnd(d, "3V3", "10uF",  ref="C_HACC2", board_tag="activation_interface")

    # ── 3 test points post-build (per system.py wakeup_board block end) ──
    tp_bat = _add_testpoint(d, ref="TP_BAT", board_tag=BTAG)
    tp_3v3 = _add_testpoint(d, ref="TP_3V3", board_tag=BTAG)
    tp_gnd = _add_testpoint(d, ref="TP_GND", board_tag=BTAG)
    _net(d, "BAT_PROT").connect(tp_bat.pin("1"))
    _net(d, "3V3")     .connect(tp_3v3.pin("1"))
    _net(d, "GND")     .connect(tp_gnd.pin("1"))


# ── main ──────────────────────────────────────────────────────────────────

def _prime_power_rails(d: Design) -> None:
    """Pre-create every known power + ground net + clock net up-front
    so the smash-side wiring helpers (cap_to_gnd / res_between /
    ind_between in `smash.netlist`) find them via
    `design.net_by_name(...)` and don't accidentally re-create them as
    `kind="signal"` later via `design.connect(name)`. Mirrors the
    `_AUTO_POWER_RAILS` map but eager — guarantees pin/net-kind
    validators see consistent kinds for every connection."""
    for name, v in _AUTO_POWER_RAILS.items():
        _net(d, name, kind="power", voltage_v=v)
    # ── absorbed flight sensors (wakeup+flight consolidation) ────────
    # The IMU/mag cluster folds onto this tile — each aft tile had only a few
    # chips left after flight control moved onto the MP25 M33. build_flight_board
    # tags the sensors board_tag="wakeup_board"; its TCAN (activation_interface)
    # and QPD TIAs (qpd_module) keep their own tags. Sensor INT/I2C nets that used
    # to cross the wakeup↔flight gap are now local to this tile.
    build_flight_board(d, board_tag="wakeup_board")

    for name in _AUTO_GROUND_NETS:
        _net(d, name, kind="ground")
    # Clock nets — frequencies sourced from the oscillator datasheets
    # and cross-validated against MCU clock-input ranges by the
    # `_v_clock_pin_frequency` validator.
    d.add_clock_net("HSE_IN",       frequency_hz=8_000_000)   # legacy / unused (orphaned — H562 retired)
    d.add_clock_net("LSE_IN",       frequency_hz=32_768)      # legacy / unused (orphaned — H562 retired)
    d.add_clock_net("WBA_HSE_IN",   frequency_hz=32_000_000)  # DSC1001 32 MHz → WBA55 OSC_IN
    d.add_clock_net("COMP_HSE_IN",  frequency_hz=40_000_000)  # DSC1001 40 MHz → MP25 OSC_IN (HSE)
    d.add_clock_net("COMP_LSE_IN",  frequency_hz=32_768)      # SiT1630 32.768 kHz → MP25 OSC32_IN (LSE)


# ── board configurations ───────────────────────────────────────────────
# Each named configuration is a subset of the snake, listed in fold order.
# `build_config_panel` folds just those boards (+ inline spacers) and we
# export one <config>.kicad_pcb per entry. To add a config, list its
# board tags here; the builder for each must exist in _BOARD_BUILDERS.
_BOARD_BUILDERS = {
    "power_board":          lambda d: build_power_board(d),
    "wakeup_board":         lambda d: build_wakeup_board(d),  # IMU/mag sensors folded in
    "fin_ble_board":        lambda d: build_fins_module(d),  # fins-only tile (2026-07-30 crowding split off wakeup; the WBA cluster moved back to wakeup_board 2026-07-31)
    "radar_module":         lambda d: build_radar_module_awr1843aop(d),
    "companion_compute":    lambda d: build_companion_compute(d),
    "nose_cap":             lambda d: build_nose_cap(d),
    "aft_end_board":        lambda d: build_aft_end_board(d),
    "cell_floor_board":     lambda d: build_cell_floor_board(d),
    "activation_interface": lambda d: build_activation_interface(d),
    "camera_module":        lambda d: build_camera_module(d),
    "qpd_module":           lambda d: build_qpd_module(d),
    "yagi_ant_a_flex":      lambda d: build_yagi_antenna_a_flex(d),
    "yagi_ant_b_flex":      lambda d: build_yagi_antenna_b_flex(d),
}

# Snake fold order (rigid boards). A config's snake is this list filtered
# to the boards it contains; the fold solver compacts whatever remains.
# Post-consolidation the MP25 (companion_compute) is the single hub. wakeup_board
# carries the flight IMU/mag sensors (the two thin aft tiles merged) AND the
# WBA55 (back 2026-07-31 — wake/activation_unlock consolidation; core_radar dropped
# fin_ble_board at the time), so wakeup→hub carries the WBA (~9 nets) + sensor
# I2C/ADC/INT (~17) traffic; the fin actuators + the piezo launch cluster
# sit one tile aft on fin_ble_board (2026-07-30 crowding split; the piezo
# came in the 2026-07-31 stack reorder that made the tile the battery
# ceiling) whose →hub run is the fin SYS_SPI (~5) + COMP_OUT, and whose
# AFT side feeds the battery column (BAT_CELL*_POS from the + contact
# lands). compute sits adjacent to its two heaviest peers — power_board
# (the STPMIC25 COMP_* rails) and radar_module (the RGMII bus); the adaptive
# land densify widens the aft→hub runs across the intervening gaps as needed.
_MASTER_SNAKE = [
    "aft_end_board", "activation_interface", "cell_floor_board", "fin_ble_board",
    "wakeup_board", "power_board", "companion_compute",
    "radar_module", "nose_cap",
]
# Branch tiles → (parent board, flex length mm, branch_side, s_fold).
# branch_side is "N" / "S" / "W" / "E" / None (None = inherit the panel-default).
# E/W are only free on the snake's END tiles (the root's west edge, the tail's
# east edge — mid-tiles use E/W for the snake), so they give an end-tile branch
# its own meridian. s_fold=False (Yagi tiles) means the leaf sits DIRECTLY
# perpendicular to the snake; s_fold=True tucks it alongside the snake flex.
_BRANCH_PARENT = {
    "yagi_ant_a_flex":  ("wakeup_board", 60.0, "N", False),
    "yagi_ant_b_flex":  ("wakeup_board", 60.0, "S", False),
    # qpd N / camera S in EVERY build (matching the maximalist panel,
    # where both coexist): the companion's flex-launch strips must sit
    # at the SAME spot in every config so the board routes ONCE — a
    # per-config side flip would move the strip and fork the layout.
    "qpd_module":       ("companion_compute", 70.0, "N", False),
    "camera_module":    ("companion_compute", 70.0, "S", False),  # mutually excl.
}

# Branch-flex launch CONTRACT — the fixed companion-side interface
# (strip side + alphabetical net order = pad order) carried by
# companion_compute in EVERY config, leaf present or not (an
# unpopulated "connector" at the flex mouth — the whole point is that
# the companion layout never changes between configs). Sides must
# match _BRANCH_PARENT + the maximalist build_panel declarations; the
# net list is validated against the live census whenever the leaf IS
# in the build, so a leaf-builder net change breaks generation loudly
# instead of silently moving pads.
_FLEX_LAUNCH_CATALOG = [
    ("companion_compute", "qpd_module", "N",
     ["3V3", "FLEX_GND", "QPD_TIA_A", "QPD_TIA_B", "QPD_TIA_C",
      "QPD_TIA_D"]),
    ("companion_compute", "camera_module", "S",
     ["CAM_CSI_CLK_N", "CAM_CSI_CLK_P", "CAM_CSI_D0_N", "CAM_CSI_D0_P",
      "CAM_CSI_D1_N", "CAM_CSI_D1_P", "CAM_EXTCLK", "COMP_1V2",
      "COMP_1V8", "COMP_2V8", "FLEX_GND"]),
]

# Canonical order configurations, from components.md "Order
# Configurations" + the config matrix. Board names mapped to twin tags;
# power_board is present in every variant (carries the COMP rails). QPD
# Si/InGaAs are the same board, so they share one layout. Each entry is the
# full board set.
# Consolidation: the STM32MP25 is the SINGLE brain (M33 = flight controller,
# A35/NPU = perception), so companion_compute is in EVERY config — there is no
# more "with/without companion" hardware split. The flight IMU/mag sensors fold
# onto wakeup_board (the two thin aft tiles merged), so there is no separate
# flight_board tile. The fin actuators also fold onto wakeup_board (no separate
# fins_module tile — its FINBOOST 12 V boost came along), so they are carried in
# EVERY config: there is no unguided/guided split, and configs differ ONLY by
# PAYLOAD / seeker (radar / qpd / camera). "core" IS the guided base.
_CORE      = {"aft_end_board", "cell_floor_board", "power_board",
              "activation_interface", "fin_ble_board", "wakeup_board",
              "companion_compute", "yagi_ant_a_flex", "yagi_ant_b_flex"}
# fin_ble_board is in EVERY config, core_radar included (2026-07-31 user
# decision, reversing the 2026-07-30 drop: since the same-day stack reorder
# the tile is the battery-compartment CEILING — cell + contact lands — and
# hosts the piezo launch cluster, both core functions, so no config may
# lose it). core_radar still flies RF-dark: it sheds only the two Yagi
# leaves (their parent wakeup_board STAYS; no BLE session without antennas).
# The wake/activation_unlock ladder (power_states.md) is unaffected: the WBA orchestrator +
# every wake listener ride wakeup_board, and the IR service-link optics ride
# radar_module — all present in core_radar.
_YAGI_LEAVES = {"yagi_ant_a_flex", "yagi_ant_b_flex"}
# nfc_antenna_flex REMOVED 2026-07-30 with the whole NFC subsystem (tag +
# antenna + wake legs) — wake channels are now magnetic / jumpstart / USB.
# The radar forward-end: the AWR2E44P tile + the nose_cap that closes the nose
# (USB-C + LEDs + waveguide-disk mount). nose_cap is RADAR-ONLY — non-radar
# configs have no post-potting service tile (they end at companion_compute).
_RADAR     = {"radar_module", "nose_cap"}

# ── battery variant ──────────────────────────────────────────────────
# DEFAULT FLIPPED 2026-07-28 (battery review): ALL configs now default to the
# 3× TLM-1520HPM/S pack stood VERTICAL (375 mAh). Under the radar-idle Ready
# floor (~110 mA) the single cell cannot carry the 1 h active-operations
# requirement with useful shelf life (tools/simulate_battery_mission.py: 1 h
# to ~5 y shelf on the best single cell vs ~12 y on the pack). The old
# default — 1× TLM-1530M/S laid HORIZONTAL (15.1 mm compartment, ~15 g
# lighter, gun-hardened 20 kgₙ tested) — survives as the `core_1cell` opt-in
# for no-radar optical builds. ⚠ The TLM-1520HPM's own gun-launch rating is
# NOT datasheet-confirmed (Preliminary 2016) — open Tadiran qualification item.
# BATTERY REWORK 2026-07-30: the cells are ordered with SIDE solder tabs (no
# end pins). Triple mode: the pack stands on the reinstated THIN
# cell_floor_board (6L / ~0.85 mm, NO coin — briefly deleted the same day,
# but cells directly on aft_end starved the aft LGA joint and pushed the
# comparator off the piezo's face); its − tab lands sit inside the cell bore
# circles, the + contacts ride the fin_ble_board ceiling (2026-07-31 stack
# reorder), and the tile passes the potting channels through to the thin
# aft gaps (activate boost / activate bank). Single mode still drops the tile
# (horizontal cell on aft_end). The active mode is a module global
# ("triple" default);
# build_power_board (tab lands), _mark_battery_pockets (cavity), the
# compartment depth, and _config_boards (cell_floor drop) all read it. Any
# code that builds a config's boards/panel (config_costs, config_heights)
# calls _set_battery_mode.
_BATTERY_MODES = {
    "single": {"compartment_mm": 15.1},   # 1× TLM-1530M/S horizontal (opt-in)
    "triple": {"compartment_mm": 21.0},   # 3× TLM-1520HPM/S vertical on
                                          #   cell_floor_board (DEFAULT)
}
_BATTERY_BY_CONFIG = {"core_1cell": "single"}  # everything else = triple
_BATTERY_MODE = "triple"                          # default = maximalist 3-cell superset


def _set_battery_mode(config_name: str) -> str:
    """Select the battery variant for a config (default 'triple'). Sets the
    module global read by build_power_board + _mark_battery_pockets."""
    global _BATTERY_MODE
    _BATTERY_MODE = _BATTERY_BY_CONFIG.get(config_name, "triple")
    return _BATTERY_MODE


def _config_boards(config_name: str, board_set) -> set:
    """Boards actually built for a config. Single-cell mode (core_1cell)
    drops cell_floor_board: the one horizontal cell lies on aft_end_board
    directly, so there is no battery-floor tile."""
    bs = set(board_set)
    if _BATTERY_BY_CONFIG.get(config_name, "triple") == "single":
        bs.discard("cell_floor_board")
    return bs


def _compartment_mm() -> float:
    """Battery-compartment depth (mm) for the active battery mode."""
    return _BATTERY_MODES[_BATTERY_MODE]["compartment_mm"]


# Every config is "core (guided base) + ONE seeker". The seekers are MUTUALLY
# EXCLUSIVE — 77 GHz radar interferes with the optical seekers (qpd / camera), and
# qpd vs camera share the optics bay — so each config carries at most one seeker;
# there are no radar+seeker combos. fin_ble_board (fins + battery ceiling +
# piezo launch cluster) rides in EVERY config since 2026-07-31; core_radar
# is RF-dark and sheds only the two Yagi leaves (the WBA wake orchestrator
# stays, on wakeup_board, so the full power_states.md ladder works in every
# config).
CONFIGS: dict[str, set[str]] = {
    "core":         _CORE,                          # no seeker
    "core_radar":   (_CORE | _RADAR) - _YAGI_LEAVES,  # RF-dark: no BLE/Yagi
    "core_qpd":     _CORE | {"qpd_module"},
    "core_camera":  _CORE | {"camera_module"},
    # Same boards as "core", but OPTS IN to the legacy single horizontal
    # TLM-1530M/S (200 mAh, 15.1 mm compartment) instead of the 3-cell
    # default — for no-radar optical builds where the Ready floor
    # stays µA-to-25 mA class. Keyed by name in _BATTERY_BY_CONFIG, not by
    # the board set. (Default flip 2026-07-28: `core_3cell` and
    # `core_radar_3cell` are gone — every config is 3-cell now, so those
    # names became aliases of `core` / `core_radar`.)
    "core_1cell":   _CORE,
}




# ── STEP export of chip-bearing PCBs (via kicad-cli) ────────────────────
# Spacers get true 4 mm bodies from cadquery (write_all_spacer_steps); the
# chip-bearing panels/configs get their 3D bodies from KiCad itself. The
# CLI is resolved once and cached; if it's missing (e.g. CI without KiCad)
# STEP export is skipped and the rest of the generation proceeds. Set
# SMASH_STEP_EXPORT=0 to skip ALL 3D STEP output — the kicad-cli tile STEPs
# AND the cadquery spacer bodies + folded-tower stackup — for fast
# netlist/panel iteration, even when kicad-cli / cadquery are present.
_STEP_ENABLED = os.environ.get("SMASH_STEP_EXPORT", "1") != "0"
# Manufacturing outputs: per-tile Gerbers + Excellon drill + one
# <tile>_gerbers.zip, plotted via kicad-cli next to each tile's
# .kicad_pcb (maximalist + every config). Independent of the STEP gate
# (a netlist-fast SMASH_STEP_EXPORT=0 run can still emit fab data);
# skipped with a note when kicad-cli is absent. SMASH_GERBER_EXPORT=0
# turns it off.
_GERBER_ENABLED = os.environ.get("SMASH_GERBER_EXPORT", "1") != "0"
# Output root is dist/. The EVB panel and the folded-tower stackup sit
# at that root; each CONFIG is a folder of per-board subdirs
# (dist/core_radar/<tile>/ with the tile .kicad_pcb + 3D models inside).
# Maximalist per-tile dumps (the union of every config) live under
# dist/maximalist/<tile>/ so they don't collide with a config's boards.
_DIST = REPO / "dist"
_PCB_OUT = _DIST
_MAXIMALIST_DIR = _DIST / "maximalist"

# The folded-tower stackup STEP (for structural FEA) is ~14 s/cadquery
# build. The full panel always emits it; per-config stackups land at
# <config>/stackup.step too by default (each config is self-contained),
# at a few minutes/regen — set SMASH_STACKUP_ALL=0 to skip them for fast
# iteration.
_STACKUP_ALL = os.environ.get("SMASH_STACKUP_ALL", "1") != "0"

# Radar (AWR1843AOP) security tier. Default OFF = the General orderable
# (AWR1843ARBGALPQ1) for prototypes/bring-up — no secure boot, easy sourcing.
# SMASH_RADAR_SECURE=1 selects the pin-identical Secure orderable
# (AWR1843ARBSALPQ1: encrypted+authenticated boot) for fielded/production units,
# REQUIRED because the radar boots from external flash. See add_awr1843aop.
_RADAR_SECURE = os.environ.get("SMASH_RADAR_SECURE", "0") == "1"

# Per-reflow board-to-board stack-assembly .kicad_pcb files (each tile/spacer
# placed as a "chip" onto the one below — for the fab's SMT board-to-board
# assembly). Opt-in via SMASH_GEN_ASSEMBLIES=1; written per config under
# dist/assembly/<config>/.
_GEN_ASSEMBLIES = os.environ.get("SMASH_GEN_ASSEMBLIES", "0") == "1"
_ASSEMBLY_DIR = _DIST / "assembly"

# Lay the snake out as one straight East row (no box-minimising planner);
# deploy branches peel off their parent board's south edge with an
# S-turn instead of claiming a grid cell. Now the default — the
# box-minimising fold solver was folding deploy branches into the wrong
# axial slots and crossing flex links over rigid neighbours; the
# straight-line variant is geometrically what the snake actually wants
# and matches how the prior `evb_2x.py` reference EVB was laid out.
# Set SMASH_STRAIGHT_SNAKE=0 to opt back into the box-minimising planner.
_STRAIGHT_SNAKE = os.environ.get("SMASH_STRAIGHT_SNAKE", "1") == "1"


def _export_stackup(design, boards, snake_chain, out_path, tiles=None) -> str:
    """Best-effort folded-tower assembly STEP for FEA. Writes the potted
    tower (`stackup.step`) and a bare-FR4 sibling without the potting
    body (`stackup_no_potting.step`). `tiles` (grid positions) lets the
    assembler apply each tile's accordion fold pose so cavities land under
    their chips. Never raises."""
    out_path = pathlib.Path(out_path)
    nopot_path = out_path.with_name(out_path.stem + "_no_potting.step")
    try:
        r = write_stackup_step(design, boards, snake_chain, out_path,
                               tiles=tiles)
        write_stackup_step(design, boards, snake_chain, nopot_path,
                           with_potting=False, tiles=tiles)
    except ImportError:
        return "stackup skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"stackup FAILED ({type(e).__name__})"
    return (f"stackup {r['n_boards']}+{r['n_spacers']} tiles, "
            f"{r['n_components']} comp, {r['height_mm']} mm "
            f"(+ no-potting variant)")


def _export_components_stackup(boards, snake_chain, tile_step_dir, out_path,
                               tiles=None):
    """Component-render sibling of `_export_stackup` — fold the detailed per-tile
    STEPs (real component bodies, not mass boxes) into the same tower. Needs the
    tile + spacer STEPs already on disk under `tile_step_dir`. Never raises."""
    try:
        r = write_stackup_components_step(boards, snake_chain, tile_step_dir,
                                          out_path, tiles=tiles)
    except ImportError:
        return "components stackup skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"components stackup FAILED ({type(e).__name__})"
    return (f"components stackup {r['n_tiles']} tiles, {r['height_mm']} mm "
            f"-> {pathlib.Path(r['output_path']).name}")


def _export_print_stls(boards, snake_chain, out_dir, tile_step_dir=None):
    """3D-print solids: a SOLID Ø34 cylinder enclosing the system
    (consolidated_stackup.stl — the nose USB-C kept as a real component when the
    per-tile STEPs are on disk under `tile_step_dir`) + the Ø39/Ø34 housing tube
    with a sealed Ø30 floor it drops into (housing.stl). Never raises."""
    out_dir = pathlib.Path(out_dir)
    try:
        cs = write_consolidated_stackup_stl(
            boards, snake_chain, out_dir / "consolidated_stackup.stl",
            tile_step_dir=tile_step_dir)
        hs = write_housing_stl(boards, snake_chain, out_dir / "housing.stl")
    except ImportError:
        return "print STLs skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"print STLs FAILED ({type(e).__name__})"
    usb = " +USB" if cs.get("usb_retained") else ""
    return (f"print STLs: consolidated_stackup.stl "
            f"(Ø{cs['diameter_mm']:.0f}x{cs['height_mm']:.1f}mm{usb}) + housing.stl "
            f"(Ø{hs['inner_dia_mm']:.0f}/{hs['outer_dia_mm']:.0f}x{hs['height_mm']:.1f}mm,"
            f" Ø{hs['floor_dia_mm']:.0f} floor)")


def _resolve_awr_placement(boards):
    """The resolved U_AWR placement on radar_module as `((cx,cy), rot_deg)`,
    or None when there is no radar tile / chip (non-radar configs). Mirrors
    `_mark_radar_block_cutout`'s chip_placements access."""
    radar = boards.get("radar_module")
    if radar is None:
        return None
    for p in radar.chip_placements:
        if getattr(p.item, "ref", None) == "U_AWR":
            return p.position_mm, (getattr(p, "rotation_deg", 0.0) or 0.0)
    return None


def _export_waveguide_stubs(boards, out_path) -> str:
    """Best-effort WR-10 throat-stub STEP for visual alignment over the
    AWR2E44P launches. Reads the resolved U_AWR placement and maps the chip's
    footprint launches into the nose_cap frame (identity fold, see
    `_mark_radar_block_cutout`). The export stacks the AWR footprint context
    (package body + BGA balls + plain verification PCB) DOWN from the launch
    plane so the stubs can be confirmed against the ball grid — no board sits
    between the launches and the stubs. Skips cleanly on non-radar configs /
    no cadquery; never raises. Call AFTER place_design + _mark_radar_block_cutout."""
    if not _STEP_ENABLED:
        return "waveguide stubs skipped (STEP off)"
    pl = _resolve_awr_placement(boards)
    if pl is None:
        return "waveguide stubs skipped (no radar tile / U_AWR)"
    # The stubs model the AWR2E44P's on-package waveguide launches. The AoP
    # (antenna-on-package) and AWR2944 (external patches) have no launches, so
    # skip — there is nothing to couple into a horn block; the nose_cap is a
    # radome for those parts, not a waveguide block.
    radar = boards.get("radar_module")
    awr_pn = next((getattr(p.item, "manf_pn", "") or "" for p in radar.chip_placements
                   if getattr(p.item, "ref", None) == "U_AWR"), "")
    if "AWR2E44P" not in awr_pn:
        return (f"waveguide stubs skipped (U_AWR={awr_pn or '?'} has no "
                f"launches — AoP/2944 use a radome, not a waveguide block)")
    (cx, cy), rot = pl
    try:
        from smash.export.waveguide_step import write_waveguide_step
        r = write_waveguide_step(
            out_path,
            placement_position_mm=(cx, cy),
            placement_rotation_deg=rot,
        )
    except ImportError:
        return "waveguide stubs skipped (no cadquery)"
    except Exception as e:                       # keep generation resilient
        return f"waveguide stubs FAILED ({type(e).__name__}: {e})"
    return (f"waveguide stubs {r['n_stubs']} @ U_AWR "
            f"({cx:.2f},{cy:.2f},{rot:.0f}deg) -> {pathlib.Path(out_path).name}")


@functools.lru_cache(maxsize=1)
def _step_cli():
    if not _STEP_ENABLED:
        return None
    try:
        return find_kicad_cli()
    except KiCadCliNotFound:
        return None


@functools.lru_cache(maxsize=1)
def _gerber_cli():
    """kicad-cli for fab plots — own gate (SMASH_GERBER_EXPORT), so a
    fast SMASH_STEP_EXPORT=0 run still emits manufacturing data."""
    if not _GERBER_ENABLED:
        return None
    try:
        return find_kicad_cli()
    except KiCadCliNotFound:
        return None


# ── economies-of-scale reference (maximalist → configs) ────────────────
# The maximalist build is the CANONICAL geometry: every board, joint and
# cutout it fabs is the one shared part. main() fills this after the
# maximalist build; _generate_config() injects it so each reduced config
# fabs the identical artifacts — same chip placements, same LGA land
# fields + nets, same milled cavities, same outline chords — instead of
# recomputing them from its own (different) census. Divergence would mean
# a per-config part number and no economies of scale.
_MAX_REF: dict | None = None


def _chain_neighbors(chain: list, bname: str) -> tuple:
    """(prev, next) chain elements around `bname` (None at the ends or when
    the board is off-chain, e.g. a branch leaf)."""
    if bname not in chain:
        return (None, None)
    i = chain.index(bname)
    return (chain[i - 1] if i > 0 else None,
            chain[i + 1] if i + 1 < len(chain) else None)


def _battery_column_conforms(panel, ref) -> bool:
    """True when this config's battery-spacer column sits in the SAME chain
    context as the maximalist reference: identical spacer list AND identical
    end boards. The column is all-or-nothing — its guarantee is ONE shared
    land pattern up the whole run (through-vias stack pad-to-pad), so a
    config whose column moved or shrank (core_1cell) must recompute EVERY
    battery joint from its own bore rather than mix replayed and fresh
    patterns mid-column."""
    max_chain = ref.get("chain") or []
    cfg_chain = list(getattr(panel, "snake_chain", []) or [])
    mb = [n for n in max_chain if n.startswith("spacer_battery")]
    cb = [n for n in cfg_chain if n.startswith("spacer_battery")]
    if not cb:
        return True
    if cb != mb:
        return False

    def _ends(chain, bs):
        i0, iN = chain.index(bs[0]), chain.index(bs[-1])
        return (chain[i0 - 1] if i0 > 0 else None,
                chain[iN + 1] if iN + 1 < len(chain) else None)

    return _ends(max_chain, mb) == _ends(cfg_chain, cb)


def _reference_conforming(panel, boards, ref) -> tuple[set, list]:
    """Boards whose chain adjacency matches the maximalist reference —
    the ones that may inherit its cavities/outline verbatim. A rigid tile
    conforms when each neighbour is the maximalist one OR absent (chain
    truncation); a spacer must match both neighbours exactly, and battery
    spacers additionally require the whole column to conform (see
    _battery_column_conforms). Returns (conforming, non_conforming_names)."""
    max_chain = ref.get("chain") or []
    cfg_chain = list(getattr(panel, "snake_chain", []) or [])
    batt_ok = _battery_column_conforms(panel, ref)
    ok, bad = set(), []
    for bname, b in boards.items():
        if bname not in (ref.get("cavities") or {}):
            bad.append(bname)          # board unknown to maximalist
            continue
        mp, mn = _chain_neighbors(max_chain, bname)
        cp, cn = _chain_neighbors(cfg_chain, bname)
        if getattr(b, "is_spacer", False):
            conforms = (cp == mp and cn == mn)
            if bname.startswith("spacer_battery"):
                conforms = conforms and batt_ok
        else:
            conforms = (cp in (mp, None)) and (cn in (mn, None))
        (ok.add(bname) if conforms else bad.append(bname))
    return ok, sorted(bad)


def _replay_absent_joint_fields(d, panel, boards, ref) -> int:
    """Tile-face land fields for maximalist joints whose SPACER this config
    omits (chain truncation): the shared board still fabs the identical
    copper, so the field is emitted from the reference verbatim (its nets
    become stubs where the mating board is absent). A face already claimed
    by a DIFFERENT joint in this config (novel adjacency, e.g. core_1cell's
    re-ordered battery column) is skipped with a warning — that board
    cannot stay identical to the maximalist part. Call right after
    place_lga_lands (before _drop_radar_nose_spacer prunes the chain)."""
    from smash.parts.connectors import _emit_land_field
    chain = list(getattr(panel, "snake_chain", []) or [])
    idx = {n: i for i, n in enumerate(chain)}
    n = 0
    for jname, J in (ref.get("joints") or {}).items():
        if jname in idx:               # joint present → place_lga_lands
            continue
        for bname, pts, face, step in ((J["before"], J["Qb"], "top", +1),
                                       (J["after"], J["Qa"], "bottom", -1)):
            b = boards.get(bname) if bname else None
            if b is None or getattr(b, "is_spacer", False):
                continue
            i = idx.get(bname)
            nb = (chain[i + step]
                  if i is not None and 0 <= i + step < len(chain) else None)
            if nb is not None:
                print(f"  WARNING: {bname} {face} face mates {nb} in this "
                      f"config, not the maximalist joint {jname} — the "
                      f"board diverges from the shared part", file=sys.stderr)
                continue
            prefix = "J_" if face == "top" else "P_"
            _emit_land_field(d, b, f"{prefix}{bname}_{jname}", pts,
                             J["nets"], face,
                             connect=lambda net, pin: _net(d, net).connect(pin))
            n += 1
    return n


def _export_tile_steps(design, panel, boards, out_dir,
                       cutouts_ref: dict | None = None) -> str:
    """Export each rigid board *tile* to its own STEP in `out_dir` —
    write a single-tile .kicad_pcb (with its flex-launch cutouts, which
    depend on the board's neighbours in this panel/config) then
    kicad-cli it. The assembled-panel STEP fuses every tile into one
    body; per-tile STEPs are far easier to inspect. Spacers get their
    fab set here too (.kicad_pcb + gerbers + _cam.md; 3D bodies stay
    with cadquery). A sibling `.stl` is dropped next to each
    `.step` for the 3D-print toolchain (see `documentation/
    3d_printing.md`). Never raises; returns a log fragment."""
    cli = _step_cli()   # None when SMASH_STEP_EXPORT=0 or kicad-cli absent;
                        # the per-board .kicad_pcb still get written either way
    out_dir.mkdir(parents=True, exist_ok=True)
    # Per-link flex widths feed the chord-cutout sizing; compute once.
    from smash.layout.placer.flex_sizing import compute_link_widths
    from smash.export.layered_step import write_layered_board_step
    from smash.export.portable_project import write_portable_project
    from smash import default_fab_profile
    link_widths, _ = compute_link_widths(design, panel)
    fab = default_fab_profile()
    ok, ok_stl, ok_layered, failed, failed_stl, failed_layered = (
        0, 0, 0, [], [], [])
    n_pcb = 0
    written: list[pathlib.Path] = []   # → portable projects, after the exports
    gcli = _gerber_cli()   # None when SMASH_GERBER_EXPORT=0 or kicad-cli absent
    ok_gerber, failed_gerber = 0, []
    for name, b in boards.items():
        if getattr(b, "is_spacer", False):
            # Spacer interposers get a fab set too — .kicad_pcb (2-layer:
            # outline + NPTH + LGA lands + filled through-vias + Eco1/Eco2
            # pocket outlines) + gerbers + the _cam.md callout, so an
            # unrouted fit-check run can be ordered without the 3D
            # pipeline. Their STEP/STL bodies stay cadquery territory
            # (write_all_spacer_steps); no panel arg — a spacer has no
            # flex-launch chords to notch.
            if b.geometry is None:
                continue
            tile_dir = out_dir / name
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_pcb = tile_dir / f"{name}.kicad_pcb"
            write_kicad_pcb(design, b, tile_pcb)
            write_blank_drawing_sheet(tile_pcb)
            written.append(tile_pcb)
            n_pcb += 1
            from smash.export.spacer_step import write_spacer_cam_notes
            write_spacer_cam_notes(b, tile_dir / f"{name}_cam.md",
                                   thickness_mm=b.thickness_mm)
            if gcli is not None:
                try:
                    write_gerbers(tile_pcb, b, kicad_cli=gcli)
                    ok_gerber += 1
                except Exception as e:           # keep run resilient
                    failed_gerber.append(f"{name}({type(e).__name__})")
            continue
        if getattr(b, "kind", "rigid") == "flex":
            # Flex antenna tiles (nfc + the two Yagi tiles) are polyimide
            # carriers — they're meant to bend around the sonde body,
            # not be FDM-printed as solid parts. Skip both STEP and STL.
            # (camera_module / qpd_module are RIGID sensor tiles on flex
            # connectors, so they fall through and DO get exported.)
            continue
        if b.geometry is None:        # no outline to build a body from
            continue
        # board-per-folder layout: each tile lives in its own out_dir/<name>/
        tile_dir = out_dir / name
        tile_dir.mkdir(parents=True, exist_ok=True)
        tile_pcb = tile_dir / f"{name}.kicad_pcb"
        write_kicad_pcb(design, b, tile_pcb, panel=panel,
                        link_widths_mm=link_widths,
                        cutouts_override=(cutouts_ref or {}).get(name))
        write_blank_drawing_sheet(tile_pcb)
        written.append(tile_pcb)
        n_pcb += 1
        # Manufacturing set: gerbers/ + <name>_gerbers.zip beside the pcb.
        if gcli is not None:
            try:
                write_gerbers(tile_pcb, b, kicad_cli=gcli)
                ok_gerber += 1
            except Exception as e:               # keep run resilient
                failed_gerber.append(f"{name}({type(e).__name__})")
        if cli is None:
            continue   # per-board .kicad_pcb written; STEP/STL export off
        step_path = tile_dir / f"{name}.step"
        try:
            write_kicad_step(tile_pcb, step_path, kicad_cli=cli)
            ok += 1
        except Exception as e:                         # keep run resilient
            failed.append(f"{name}({type(e).__name__})")
            continue
        # STL — read back the STEP, split at the PCB midplane (so the
        # cut goes through FR4 substrate, not through chip bodies),
        # stamp a 2-char pairing-aid symbol (raised on the bottom
        # half's outer face, recessed on the top half's outer face),
        # and write `<name>_top.stl` + `<name>_bot.stl`. Each half
        # prints flat-down on the bed with no supports. Tile-specific
        # tolerance (0.3 mm linear, below a 0.4 mm FDM nozzle's print
        # resolution) keeps the per-component 3D models embedded by
        # kicad-cli from bloating output files.
        try:
            from smash.export.stl import (
                write_split_stls_from_step, unique_symbol,
                TILE_TOLERANCE_MM, TILE_ANGULAR_TOLERANCE,
            )
            # Stale single-STL from a previous build at the old shape.
            for old in (tile_dir / f"{name}.stl",):
                if old.exists():
                    old.unlink()
            write_split_stls_from_step(
                step_path, tile_dir / name,
                z_split=b.thickness_mm / 2,
                tolerance=TILE_TOLERANCE_MM,
                angular_tolerance=TILE_ANGULAR_TOLERANCE,
                symbol=unique_symbol(name),
            )
            ok_stl += 1
        except Exception as e:
            failed_stl.append(f"{name}({type(e).__name__})")
        # Layered STEP — walk the board's stackup and emit ONE solid per
        # copper foil + per dielectric (+ optional Al backing + chip
        # blocks) with a sidecar JSON manifest that maps body name to
        # mechanical + EM properties (E, ν, ρ, ε_r, tan δ, σ). This is
        # the FEA / EM-sim ingestion format — separate bodies so the
        # mesher can assign per-layer material properties.
        if (b.stackup or []):
            try:
                write_layered_board_step(
                    b, tile_dir / f"{name}_layered.step", fab=fab,
                    with_components=True, with_al_backing=True,
                )
                ok_layered += 1
            except Exception as e:
                failed_layered.append(f"{name}({type(e).__name__})")
    # Portable projects — LAST, so kicad-cli plotted gerbers/STEP against the
    # absolute library + 3D-model paths first. Each board directory becomes a
    # standalone KiCad project: its own <Lib>.pretty, its own 3dmodels/, and
    # an fp-lib-table pointing at both, so an EE can open the board, edit a
    # footprint and "Update Footprints from Library" without this repo.
    portable_msg = ""
    if written:
        n_lib, n_mdl, warn = 0, 0, []
        for pcb in written:
            try:
                r = write_portable_project(pcb)
            except Exception as e:                 # keep the run resilient
                warn.append(f"{pcb.stem}({type(e).__name__})")
                continue
            n_lib += r["n_footprints"]
            n_mdl += r["n_models"]
            if r["missing_models"]:
                warn.append(f"{pcb.stem}: {len(r['missing_models'])} model(s) "
                            "not found")
            if r["conflicts"]:
                warn.append(f"{pcb.stem}: {', '.join(r['conflicts'])} differ "
                            "between instances")
        portable_msg = (f", portable libs {n_lib} footprints + {n_mdl} 3D models")
        if warn:
            portable_msg += "; PORTABLE WARN: " + "; ".join(warn)

    gerber_msg = (f", {ok_gerber} gerber zips" if gcli is not None
                  else ", gerbers off")
    if cli is None:
        msg = (f"{n_pcb} per-board .kicad_pcb{gerber_msg}{portable_msg} → "
               f"{out_dir.relative_to(REPO)}/ (STEP export off)")
        if failed_gerber:
            msg += f"; GERBERS FAILED: {', '.join(failed_gerber)}"
        return msg
    msg = (f"{n_pcb} .kicad_pcb, {ok} STEP{gerber_msg}{portable_msg} → "
           f"{out_dir.relative_to(REPO)}/ (+{ok_stl} STL, +{ok_layered} layered)")
    if failed:
        msg += f"; STEP FAILED: {', '.join(failed)}"
    if failed_stl:
        msg += f"; STL FAILED: {', '.join(failed_stl)}"
    if failed_layered:
        msg += f"; LAYERED FAILED: {', '.join(failed_layered)}"
    if failed_gerber:
        msg += f"; GERBERS FAILED: {', '.join(failed_gerber)}"
    return msg


_EE_LAYOUT_JSON = (pathlib.Path(__file__).parent
                   / "application/src/smash/data/companion_ee_layout.json")
_ACTIVATION_EE_JSON = (pathlib.Path(__file__).parent
                       / "application/src/smash/data/"
                         "activation_interface_ee_layout.json")
_POWER_LANDS_EE_JSON = (pathlib.Path(__file__).parent
                        / "application/src/smash/data/"
                          "power_board_ee_lands.json")


def _power_board_pinned_lands() -> dict:
    """EE-pinned LGA field for power_board's companion-side joint (Sjoert's
    routed power_board, WIP/Sjoert/power_board/; his part placements are
    pinned in locked_placements.json). Its top field came from an earlier
    land placer — two extra lands (USB_VBUS, WBA_BOOT0) shift the net order
    against today's pack — so rather than re-route the board, the spacer and
    companion_compute's bottom face adopt it; see
    `place_lga_lands(pinned=...)`, which warns if a pinned land leaves the
    joint's free region or a crossing net goes uncarried. Configs inherit
    it through the maximalist joint capture.

    The wakeup-side (bottom) field is NOT pinned: it was packed around the
    old wrong-diagonal potting holes, so 24 lands fall on the spacer's real
    holes/channel and 5 cut into the Ø3 potting holes of the board itself.
    That joint packs fresh; the board's bottom field must be redone."""
    if not _POWER_LANDS_EE_JSON.exists():
        return {}
    return json.loads(_POWER_LANDS_EE_JSON.read_text())["joints"]


def _apply_activation_reference_layout(d, boards: dict) -> None:
    """Adopt the EE's component placement for activation_interface.

    The board was routed externally (Freerouting-assisted, see
    `Finalized/activation_interface/`), so its 791 tracks, 88 vias and 4
    plane zones are drawn against THESE component positions. Re-placing
    them on a later run silently invalidates that routing, which is the
    same failure the companion reference guards against.

    Imported by `tools/import_ee_layout.py <src> --board
    activation_interface`. The delta at import time was a single part —
    L_ACTIVATE, nudged 0.29 mm during routing — so this is not about moving
    anything today. It is about pinning what the copper was drawn on, so
    the packer cannot drift the board out from under the routing when a
    footprint or a neighbour changes.

    COPPER IS IMPORTED VERBATIM — 791 tracks over 9 layers, 88 through
    vias and the 4 plane zones (FLEX_GND In1/In12, 3V3 In2, COMP_5V In11),
    all attached with note="ee-ref". Unlike companion_compute nothing is
    dropped: every component here is top-face, so the B.Cu copper is the
    EE's own routing rather than stitching for an unplaced pile.

    ⚠ WIDTH CAVEAT: Freerouting was driven from a DSN carrying ONE rule —
    100 µm track, 75 µm clearance, a single 0.45/0.20 via — so all 42 nets
    come in at 4 mil, ACTIVATE_HV (33 V) and BAT_RAW included, alongside the
    SWD pins. That is a routing input, not a considered choice, and the
    EE's own notes still list track-width DRC errors on ACTIVATE_HV, FLEX_GND,
    3V3 and NRST. Re-derive the power widths per net class before fab.

    Also NOT imported: the TN0018 keepout under U_HACC (a KiCad keepout
    zone with no net; the model has no equivalent) and the EE's
    activation_interface.kicad_dru.

    Unlike companion_compute this locks BOTH faces: the only bottom-face
    entry is the P_ land field at the origin, where it already sits, so
    there is no unplaced-pile problem to work around here."""
    b = boards.get("activation_interface")
    if b is None or not _ACTIVATION_EE_JSON.exists():
        return
    from smash.layout.locked import load_locked_placements
    data = json.loads(_ACTIVATION_EE_JSON.read_text())
    ref_place = data.get("placements") or {}
    # An explicit entry in locked_placements.json OUTRANKS the import. Those
    # carry a recorded engineering reason; a routing nudge does not get to
    # overwrite one silently. L_ACTIVATE is the live case: locked at (-7.5,-4.0)
    # on 2026-07-31 so its cavity merges with the activate-bank pocket instead of
    # notching the perimeter interconnect ring, and the EE's 0.29 mm nudge
    # puts it 0.14 mm into the spacer FR4 (check_spacer_chip_clearance
    # catches it). To adopt such a move, change the lock and its reason.
    pinned = set(load_locked_placements())
    moved = n_lock = 0
    refused = []
    for i, pl in enumerate(b.chip_placements):
        ref = getattr(pl.item, "ref", None)
        ee = ref_place.get(ref)
        if not ee:
            continue                       # MECH1/MECH2 have no model ref
        pos = tuple(ee["pos"])
        if ref in pinned and (abs(pos[0] - pl.position_mm[0]) > 1e-4
                              or abs(pos[1] - pl.position_mm[1]) > 1e-4):
            refused.append(ref)
            continue
        if (abs(pos[0] - pl.position_mm[0]) > 1e-4
                or abs(pos[1] - pl.position_mm[1]) > 1e-4):
            moved += 1
        b.chip_placements[i] = pl._replace(
            position_mm=pos, rotation_deg=ee["rot"],
            face=ee["face"], locked=True)
        n_lock += 1
    # Copper, verbatim. Every part on this tile is top-face, so there is no
    # bottom-face pile to guard against the way companion_compute needs.
    from smash.state.routing.track import Track
    from smash.state.routing.via import Via
    from smash.state.routing.zone import Zone
    for t in data.get("tracks") or []:
        b.tracks.append(Track(
            net=t["net"], layer=t["layer"], width_mm=t["width"],
            path=[tuple(q) for q in t["path"]], note="ee-ref"))
    for v in data.get("vias") or []:
        b.vias.append(Via(
            net=v["net"], position_mm=(v["x"], v["y"]),
            drill_mm=v["drill"], pad_diameter_mm=v["size"],
            from_layer=v["from"], to_layer=v["to"], kind=v["kind"],
            filled=True, note="ee-ref"))
    for z in data.get("zones") or []:
        b.zones.append(Zone(
            net=z["net"], layer=z["layer"],
            outline_mm=[tuple(q) for q in z["outline"]],
            fill_polygons_mm=[
                {"layer": f.get("layer"), "pts": [tuple(q) for q in f["pts"]]}
                for f in (z.get("fills") or [])],
            note="ee-ref"))
    widths = sorted({t["width"] for t in (data.get("tracks") or [])})
    msg = (f"activation_interface: EE reference layout applied "
           f"({n_lock} placements locked, {moved} moved, {len(b.tracks)} "
           f"tracks, {len(b.vias)} vias, {len(b.zones)} zones; "
           f"track widths {widths} mm — single-rule autoroute, re-derive "
           f"power widths before fab)")
    if refused:
        msg += (f"; REFUSED {len(refused)} that locked_placements.json pins "
                f"with a recorded reason: {', '.join(sorted(refused))}")
    print(msg)
    from smash.validators import assert_no_locked_overlaps
    assert_no_locked_overlaps(boards)


def _apply_companion_reference_layout(d, boards: dict) -> None:
    """Adopt the EE reference PLACEMENT for companion_compute.

    His TOP-face placements only — imported by tools/import_ee_layout.py
    into the board frame. The reference was laid out against THIS netlist
    (it carries our refs and net names, including the VREFCA divider +
    ALERT_N pull-up parts we already author), so it lands without netlist
    changes. Bottom-face parts are left to smash's placer (his bottom
    decaps are an unplaced pile).

    THE COPPER WAS REMOVED 2026-09-03. The `testcercacompo1306` drop is not
    manufacturable and the board is being re-routed, so carrying its 1121
    tracks / 234 vias / 8 zones meant every regeneration shipped fab data
    with routing known to be bad — and its zones carried no fill polygons,
    so the plane layers plotted as empty copper on top of that. Better to
    generate the board unrouted, where the gap is obvious, than to ship
    wrong copper. The capture is in git if it is ever wanted again.

    The PLACEMENT stays: documentation/ee_companion_compute_review.md
    accepted it ("38 major parts identical to our generated reference",
    the decaps and bias resistors properly placed and no longer a pile),
    and the re-route will be drawn against it.

    To take a new drop: re-run `tools/import_ee_layout.py <src>` — it now
    captures `filled_polygon` fills too, which the old capture predates —
    then re-add a track/via/zone attach here. Revisit two things at that
    point: the import's `_DENY` net list (companion-specific exclusions
    that may be stale once re-routed) and the old B.Cu-copper drop, which
    existed because that drop's bottom decaps were unplaced."""
    b = boards.get("companion_compute")
    if b is None or not _EE_LAYOUT_JSON.exists():
        return
    data = json.loads(_EE_LAYOUT_JSON.read_text())
    moved = 0
    for i, pl in enumerate(b.chip_placements):
        ref = getattr(pl.item, "ref", None)
        ee = data["placements"].get(ref)
        # Lock ONLY the routed TOP face. The EE hand-places the top side
        # (and we lock it) because his DDR4 copper is routed against it;
        # the BOTTOM side of every board is left to smash's placer. His
        # file leaves the bottom decoupling caps in KiCad's unplaced pile
        # — a heap of ~60 overlapping 0805s near the origin — and locking
        # those verbatim merged their pads, shorting every power rail to
        # FLEX_GND (86 DRC shorts + 272 unconnected). Bottom-face refs
        # keep their native, collision-free placement; the test-locked
        # overlap validator guards the top face. See [[ddr4-ee-layout]].
        if ee and ee.get("face") == "top":
            # Placement is a NamedTuple — replace, don't mutate
            b.chip_placements[i] = pl._replace(
                position_mm=tuple(ee["pos"]),
                rotation_deg=ee["rot"], face=ee["face"], locked=True)
            moved += 1
    print(f"companion_compute: EE reference PLACEMENT applied "
          f"({moved} top-face placements; copper REMOVED 2026-09-03 — the "
          f"drop is not manufacturable, board is being re-routed)")
    # Guard the locks we just applied: a locked part the placer can't move
    # must never overlap another component. This is what catches an EE drop
    # that locks an unplaced pile (overlapping bottom decaps -> merged pads
    # -> power-to-GND shorts) — fail the build here, not at the fab's DRC.
    from smash.validators import assert_no_locked_overlaps
    assert_no_locked_overlaps(boards)


def _mark_radar_block_cutout(boards: dict) -> None:
    """Radar coupling cutout: a through-cut in the nose_cap that FOLLOWS the
    radar's top-face chips — the central AWR (the waveguide coupling aperture)
    plus the buck / LDO / 1V0 bulk-cap ringing it — so each pokes up through the
    nose_cap, which now stacks directly on the radar. The cutout is the shapely
    UNION of each chip's footprint + clearance, projected into the nose_cap frame
    (mirror_x fold), so it HUGS the chips (non-rectangular, minimal material
    removed) instead of milling a big block. The aluminium waveguide disk/antenna
    sits on the outer face and SEALS the opening; the radar couples to it across
    the air gap. Emitted as `face="through"` CavityRegion(s) → Edge.Cuts windows,
    with matching no-place Keepouts. Isolated builds (no radar tile) fall back to
    a ~15 mm square so the aperture still renders. Call AFTER place_design."""
    nose = boards.get("nose_cap")
    if nose is None:
        return
    from shapely.geometry import box as _box, Polygon as _Poly
    from shapely.ops import unary_union
    from smash.state.board_geometry import Keepout
    from smash.state.geometry.cavity import CavityRegion
    from smash.state.topology.placement import Placement
    CLR = 0.6
    radar = boards.get("radar_module")
    boxes = []
    if radar is not None:
        for p in radar.chip_placements:
            fp = getattr(p.item, "footprint", None)
            if getattr(p, "face", None) != "top" or fp is None:
                continue
            if getattr(p.item, "ref", None) == "J_USB_C":
                continue  # USB-C pokes up through the N-chord NOTCH (kicad_pcb._tile_cuts), not a block cutout
            # Cavity extent: prefer the declared body size_mm; fall back to the
            # F.Fab body / courtyard bounding box so a top-face chip that didn't
            # declare size_mm (e.g. a SamacSys flash) still gets a cutout rather
            # than being silently skipped (which is exactly what dropped the
            # SST26 flash before).
            wh = fp.size_mm
            if not wh:
                poly = fp.body_outline or fp.courtyard
                if poly:
                    xs = [x for x, _y in poly]
                    ys = [_y for _x, _y in poly]
                    wh = (max(xs) - min(xs), max(ys) - min(ys))
            if not wh:
                continue
            cx, cy = p.position_mm
            w, h = wh
            # The nose_cap stacks DIRECTLY on the radar and the backbone lands
            # mate through the (discarded) scaffold spacer — radar→spacer→nose is
            # two mirror_x folds = IDENTITY — so a radar chip at (cx,cy) sits under
            # the nose_cap at the SAME (cx,cy). The cutout follows it there (no
            # mirror), which also keeps it clear of the folded LGA lands.
            boxes.append(_box(cx - w / 2 - CLR, cy - h / 2 - CLR,
                              cx + w / 2 + CLR, cy + h / 2 + CLR))
    if not boxes:                                 # isolated render: no radar tile
        boxes = [_box(-7.5, -7.5, 7.5, 7.5)]
    merged = unary_union(boxes)
    # Close gaps narrower than the minimum nose_cap wall so two near-but-separate
    # cutouts don't leave an unmillable thin sliver between them — they merge into
    # one window (the "combine cavities when courtyards touch" rule, generalised
    # to a min-wall threshold). Morphological close = buffer-out then buffer-in;
    # mitre join keeps the box corners square. No-op for a single cutout.
    _MIN_WALL_MM = 1.0
    closed = (merged.buffer(_MIN_WALL_MM / 2, join_style=2)
                    .buffer(-_MIN_WALL_MM / 2, join_style=2))
    if not closed.is_empty:
        merged = closed
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    rings = [[(round(x, 3), round(y, 3)) for x, y in g.exterior.coords[:-1]]
             for g in parts]

    def _apply(board, depth_mm: float, ring_list) -> None:
        # Drop any pre-existing through-cut fully inside these cut(s) (redundant —
        # a nested Edge.Cuts loop would stitch as a floating FR4 island), then add
        # the chip-hugging cut(s).
        ml = unary_union([_Poly(r) for r in ring_list])
        board.cavity_placements = [
            pl for pl in board.cavity_placements
            if not (isinstance(pl.item, CavityRegion) and pl.item.face == "through"
                    and pl.item.exterior_polygon
                    and _Poly(pl.item.exterior_polygon).within(ml))]
        for i, ring in enumerate(ring_list):
            board.cavity_placements.append(Placement(
                position_mm=(0.0, 0.0), rotation_deg=0.0, face="top",
                item=CavityRegion(name=f"radar_chip_cutout_{i}", face="through",
                                  exterior_polygon=ring, depth_mm=depth_mm)))

    _apply(nose, 0.0, rings)                      # face=through → Edge.Cuts window
    if getattr(nose, "geometry", None) is not None:
        for ring in rings:
            nose.geometry.keepouts.append(Keepout(
                polygon=ring, scope="both", tag="awr_aperture",
                note="Radar-chip coupling cutout (through-cut) — no parts over it."))
    sp = boards.get("spacer_radar_module_nose_cap")   # scaffold (discarded later)
    if sp is not None:
        # The backbone lands are packed against the SPACER's free region then
        # folded onto each neighbour via _fold(Q, same_row) — mirror_x OR mirror_y.
        # The CENTRAL cut is ~symmetric so it's fine either way, but the off-centre
        # LED lobes are not — the folded lands would clip them. Exclude all four
        # reflections of the cut on the (thrown-away) scaffold spacer so the lands
        # clear the real nose_cap cut regardless of fold parity.
        refl = [[(sx * x, sy * y) for x, y in r]
                for r in rings for sx in (1, -1) for sy in (1, -1)]
        _apply(sp, sp.thickness_mm, refl)


# Guaranteed air gap above the AWR top (~one fab layer). The aluminium waveguide
# disk mounts on the nose_cap's OUTER face; sizing the radar↔nose_cap spacer a
# touch PROUD of flush keeps the AWR top this far below the outer face, so the
# disk never presses on the chip even with stackup tolerance. The RF choke-flange
# coupling gap itself is set by the disk recess, not by this margin.
_AWR_AIR_GAP_MM = 0.13


def _mark_usb_cavity(boards: dict) -> None:
    """No-op, kept as a documented call site (and for the spacer-discard test).

    The UJ20 connector pocket used to be marked here as a separate through-cut
    CavityRegion, but it OVERLAPPED the N chord flat in the board outline and the
    outline boolean left stray FR4 rectangles in front of the connector. The
    pocket is now built INTO the outline as a central notch in the chord
    (flat -> notch -> flat, one continuous edge) -- see kicad_pcb._tile_cuts
    (notch_width_mm/notch_depth_mm on the N flat) and the matching cut in
    stackup_step.build_board_solid."""
    # No-op. The UJ20 connector pocket is now built INTO the board outline as a
    # central notch in the N chord (flat -> notch -> flat, one continuous edge) —
    # see kicad_pcb._tile_cuts (notch_width_mm/notch_depth_mm on the N flat) and
    # the matching cut in stackup_step.build_board_solid. The old approach put a
    # separate through-cut CavityRegion here that OVERLAPPED the chord flat, and
    # the outline boolean left stray FR4 rectangles in front of the connector.
    return


def _mark_preplace_keepouts(d: Design, boards: dict) -> None:
    """Keepouts the placer must see BEFORE place_design (chip_placements aren't
    set yet, so this reads the AWR from `d.chips`):

      1. The nose_cap's central AWR coupling aperture (a through-cut) — no parts
         may cluster there or they float over the cutout.
      2. The radar's NORTH column where the nose_cap USB-C lands when the snake
         folds (X-mirror → N maps to N), so no tall radar chip (e.g. the
         LMR10510 buck) ends up under the connector through the thin spacer."""
    from smash.state.board_geometry import Keepout
    nose = boards.get("nose_cap")
    if nose is not None and getattr(nose, "geometry", None) is not None:
        # The cutout (marked post-place) grows past the AWR to swallow the radar's
        # top-face power chips (buck / LDO / 1V0 bulk-cap) out to ~radius 10. Keep
        # the nose_cap's own passives clear of that whole region so they don't
        # float — the pre-place keepout anticipates the enlarged cutout. Asymmetric
        # in Y to preserve the north cap for the USB; locked LEDs/USB sit outside.
        nose.geometry.keepouts.append(Keepout(
            polygon=[(-11.5, -11.0), (11.5, -11.0), (11.5, 7.5), (-11.5, 7.5)],
            scope="both", tag="awr_aperture",
            note="Enlarged AWR + power-chip cutout (through-cut) — no parts over it."))
    radar = boards.get("radar_module")
    if radar is not None and getattr(radar, "geometry", None) is not None:
        radar.geometry.keepouts.append(Keepout(
            polygon=[(-6.0, 7.5), (6.0, 7.5), (6.0, 17.0), (-6.0, 17.0)],
            scope="both", tag="usb_zone",
            note="nose_cap USB-C lands here when folded — keep tall chips out."))

    # 3. Battery-bracket tuck (triple mode): the compartment's two bracket
    #    faces — fin_ble's BOTTOM (the ceiling) and cell_floor's TOP — must
    #    keep their parts INSIDE the cell bore (the 2026-07-31 rule: parts
    #    tuck into the ~1 mm headroom over the cell tops). Un-enforced, the
    #    packer scatters them into the perimeter land ring and
    #    _mark_battery_chip_clearance then "heals" them into a huge scalloped
    #    pocket blob cut through EVERY battery spacer (the artifact caught on
    #    the spacers 2026-08-28) while eating the column's LGA ring. The
    #    packer only understands axis-aligned keepout AABBs, so the not-bore
    #    region is rasterized into a grid of small rects; cells are blocked
    #    unless fully inside bore−0.7 mm, so a packed body (+0.3 mm clearance
    #    box) always lands ≥0.4 mm inside the through-cut and the clearance
    #    pass drops every pocket.
    if _BATTERY_MODE != "single":
        from shapely.geometry import box as _box
        bore_in = _battery_bore_polygon().buffer(-0.7)
        STEP = 1.0
        rects = []
        k = 17                      # grid spans ±17 mm (the Ø34 tile)
        for gj in range(-k, k):
            run_start = None        # merge each row's blocked cells into runs
            for gi in range(-k, k + 1):
                blocked = gi < k and not bore_in.contains(
                    _box(gi * STEP, gj * STEP,
                         (gi + 1) * STEP, (gj + 1) * STEP))
                if blocked and run_start is None:
                    run_start = gi
                elif not blocked and run_start is not None:
                    rects.append((run_start * STEP, gj * STEP,
                                  gi * STEP, (gj + 1) * STEP))
                    run_start = None
        for bname, cu in (("fin_ble_board", "B.Cu"),
                          ("cell_floor_board", "F.Cu")):
            b = boards.get(bname)
            if b is None or getattr(b, "geometry", None) is None:
                continue
            for (x0, y0, x1, y1) in rects:
                b.geometry.keepouts.append(Keepout(
                    polygon=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                    layers=(cu,), scope="component", tag="battery_bore_tuck",
                    note="battery-facing face: parts stay INSIDE the cell "
                         "bore (compartment headroom) — see "
                         "_mark_battery_chip_clearance."))


def _set_dynamic_spacer_thickness(d: Design, boards: dict) -> None:
    """Size the radar↔nose_cap spacer so the nose_cap's OUTER face clears the AWR
    top by `_AWR_AIR_GAP_MM`: spacer = AWR_height − nose_cap_thickness + air_gap.
    The AWR pokes up through this spacer + the nose_cap AWR aperture but STOPS one
    fab layer below the outer face, guaranteeing an air gap above the chip. Call
    BEFORE place_design so the cavity through-cut + stack height use the thickness.

    Other spacers keep the uniform SPACER_THICKNESS_MM for now — minimising them
    individually wants a per-gap chip-clearance pass + FEA re-validation (the
    spacer launch FEA was run at 4 mm)."""
    sp = boards.get("spacer_radar_module_nose_cap")
    nose = boards.get("nose_cap")
    if sp is None or nose is None:
        return
    awr = next((c for c in getattr(d, "chips", []) if c.ref == "U_AWR"), None)
    if awr is None:
        return
    awr_h = (getattr(awr, "height_mm", None)
             or (awr.footprint.height_mm if awr.footprint else None))
    if not awr_h:
        return
    t = round(awr_h - nose.thickness_mm + _AWR_AIR_GAP_MM, 3)
    if t > 0.0:
        sp.thickness_override_mm = t


def _drop_radar_nose_spacer(d: Design, panel, boards: dict) -> None:
    """Discard the SCAFFOLD radar↔nose_cap spacer. It's created + folded like any
    other so `place_lga_lands` lays the backbone lands on the radar TOP and
    nose_cap BOTTOM faces — each index carrying the same net, so they mate
    pad-to-pad on matching nets. But the thick nose_cap (1.455 mm) now clears the
    AWR on its own, so there is NO physical spacer between the two: after the lands
    are placed we remove it entirely — the board, its mechanical + J/P
    pass-through land chips, those chips' net pins, and its slot in the
    snake/stack. Radar and nose_cap end up directly stacked, joined by the
    surviving radar-top/nose_cap-bottom lands. Call AFTER place_lga_lands."""
    name = "spacer_radar_module_nose_cap"
    if name not in boards:
        return
    dropped = {c.ref for c in d.chips if getattr(c, "board_tag", None) == name}
    boards.pop(name, None)
    if getattr(panel, "snake_chain", None):
        panel.snake_chain = [n for n in panel.snake_chain if n != name]
    if getattr(panel, "tiles", None) and name in panel.tiles:
        panel.tiles.pop(name, None)
    d.chips = [c for c in d.chips if c.ref not in dropped]
    for net in d.nets:
        net.pins = [(ref, pn) for (ref, pn) in net.pins if ref not in dropped]


def _mark_battery_pockets(boards: dict) -> None:
    """ONE merged through-cut per battery-compartment spacer. Triple mode: a
    trefoil union of the 3 Ø14.8 vertical cells (triangle around the spin axis,
    overlapping, thin centre web filled). Single mode (lowprofile): a stadium
    for the 1 horizontal Ø15.1×27.4 cell laid along X. The LGA lands + filled
    vias pack the remaining perimeter ring. Call AFTER place_design (clears
    cavity_placements) and BEFORE place_lga_lands (so the land packer's free
    region excludes the cutout)."""
    _apply_battery_bore(boards, _battery_bore_polygon())


def _battery_bore_polygon():
    """The battery compartment bore as a shapely Polygon, in the active
    battery mode. ONE source of truth: `_mark_battery_pockets` stamps it as
    the spacers' through-cut and `_mark_preplace_keepouts` uses it to keep
    the bracket tiles' battery-facing parts tucked INSIDE it (the
    2026-07-31 rule) — the two must never drift apart."""
    import math as _m
    from shapely.geometry import Polygon as _ShPoly
    from shapely.ops import unary_union
    n = 48

    def _circle(cx, cy, r):
        return [(cx + r * _m.cos(2 * _m.pi * i / n),
                 cy + r * _m.sin(2 * _m.pi * i / n)) for i in range(n)]

    if _BATTERY_MODE == "single":
        # one horizontal cell → a RECTANGLE (its true top-down projection — the
        # cylinder has FLAT ends, so the silhouette is L×Ø, not a stadium). Laid
        # with its LONG axis along the potting-hole axis (the two activation
        # holes are 180° apart) so the cell bore and potting channel coincide.
        CELL_D, CELL_L, CLR = 15.1, 27.4, 0.4
        # Cell long axis VERTICAL (N–S). The compartment was meant to follow the
        # potting axis, but that potting channel is gone from the battery spacers
        # (see _apply_battery_bore), and KiCad handles an axis-aligned cell far
        # better than a diagonal one — so the cell is laid straight N–S. Its
        # end-tab via-tabs P_CELL_TAB_POS/NEG sit at the N/S ends (0, ±13.9).
        theta = _m.radians(90.0)
        L2, W2 = (CELL_L + CLR) / 2.0, (CELL_D + CLR) / 2.0
        _ct, _st = _m.cos(theta), _m.sin(theta)
        return _ShPoly([(x * _ct - y * _st, x * _st + y * _ct)
                        for x, y in [(-L2, -W2), (L2, -W2), (L2, W2), (-L2, W2)]])
    CELL_R, CLUSTER_R = 7.6, 8.6     # Ø14.8 cell + ~0.4 clr; triangle radius
    centres = [(CLUSTER_R * _m.cos(_m.pi / 2 + 2 * _m.pi * k / 3),
                CLUSTER_R * _m.sin(_m.pi / 2 + 2 * _m.pi * k / 3))
               for k in range(3)]
    bore = unary_union([_ShPoly(_circle(cx, cy, CELL_R)) for cx, cy in centres])
    if bore.geom_type != "Polygon":      # not connected → enclose them
        bore = bore.convex_hull
    return bore


def _apply_battery_bore(boards: dict, bore) -> None:
    """Stamp a battery bore polygon onto every spacer_battery_* tile and thread
    EVERY perimeter potting hole through the whole column to the aft floor.

    A hole whose centre sits past the bore (in the perimeter ring) is CONTINUED
    as a through-channel down every battery spacer and tied into the bore by a
    finger on the aft-most spacer (spacer_battery_1); a hole already inside the
    bore just vents straight into it and needs neither. The projected holes come
    from the run's RIGID bracket tiles (triple: cell_floor + the fin_ble ceiling
    since the 2026-07-31 reorder; single: aft_end + activation). For the single
    cell BOTH ceiling holes sit just past the bore's short-edge ends (r≈14 vs
    the bore's 13.9), so both become full-length channels to the aft floor —
    potting injected at one fills the cell cavity upward and vents out the
    other; they already carry the spacer fold mirror, so they land under the
    real tile holes. (The 3-cell trefoil has one hole inside a lobe → only
    the other, outside, hole is threaded.)"""
    from shapely.geometry import LineString as _LS, Point as _ShPt
    from shapely.ops import unary_union
    from smash.state.geometry.cavity import CavityRegion
    from smash.state.topology.placement import Placement
    from smash.layout.cavities import (POTTING_CHANNEL_WIDTH_MM as _PW,
                                       POTTING_HOLE_DIA_MM as _PHD)
    from smash.state.board_geometry import Hole

    # Every distinct perimeter (outside-bore) potting hole across the column —
    # each gets its own full-length channel + bore finger. Deduped by position
    # (holes are only projected onto the spacers adjacent to a RIGID end tile —
    # activation_interface, and in triple mode the cell_floor floor tile, whose
    # projections coincide; sibling-spacer projection is skipped in
    # attach_cavities_to_spacers — but the channel is replicated onto all of
    # them below). Thread EVERY perimeter potting hole straight DOWN through
    # every battery spacer as a through-drill, so the end tiles' potting holes
    # continue all the way down the column to the aft floor. (These holes are
    # outside the bore, in the land ring.)
    channels: list = []
    vents: list = []
    for nm, b in boards.items():
        if not nm.startswith("spacer_battery") or b.geometry is None:
            continue
        for h in b.geometry.holes:
            if getattr(h, "tag", None) != "potting":
                continue
            xy = (round(h.position_mm[0], 4), round(h.position_mm[1], 4))
            if not bore.contains(_ShPt(*h.position_mm)):
                if xy not in channels:
                    channels.append(xy)
            elif xy not in vents:
                vents.append(xy)
    # A vent hole whose CENTRE is inside a bore lobe can still poke its Ø3
    # circle a hair past the bore 48-gon chord (fin_ble's SE hole sits 6.11 mm
    # from the 330° cell centre → circle reaches 7.61 vs the 7.6 bore). Left
    # alone, the tile's drill then ends on a ~0.25 mm sliver LEDGE of spacer
    # FR4 — unmillable, and the lens-shaped potting facet breaks the
    # full-stack FEA's fragment imprint (gmsh 'overlapping facets'). Swallow
    # each vent's full disc (+0.3 clearance) into the bore so the vent drops
    # cleanly into the compartment.
    if vents:
        bore = unary_union(
            [bore] + [_ShPt(*xy).buffer(_PHD / 2.0 + 0.3, quad_segs=16)
                      for xy in vents])
        if bore.geom_type != "Polygon":
            bore = bore.convex_hull
    bore_plain = [(x, y) for x, y in bore.exterior.coords][:-1]
    # Tie each through-drill into the cell compartment with a finger on the AFT-MOST
    # spacer (spacer_battery_1) only. Single vertical cell: a SHORT cutout from the
    # drill to the NEAREST bore edge (a small breach into the compartment, NOT the
    # long diagonal centre finger). Multi-cell: the original centre finger.
    if channels:
        if _BATTERY_MODE == "single":
            fingers = []
            for xy in channels:
                near = bore.exterior.interpolate(bore.exterior.project(_ShPt(*xy)))
                fingers.append(_LS([xy, (near.x, near.y)]).buffer(_PW / 2.0))
            fingered = unary_union([bore] + fingers)
        else:
            fingered = unary_union([bore] + [_LS([(0.0, 0.0), xy]).buffer(_PW / 2.0)
                                             for xy in channels])
        if fingered.geom_type != "Polygon":
            fingered = fingered.convex_hull
        bore_fingered = [(x, y) for x, y in fingered.exterior.coords][:-1]
    else:
        bore_fingered = bore_plain

    for nm, b in boards.items():
        if not nm.startswith("spacer_battery"):
            continue
        # Only the aft-most battery spacer (spacer_battery_1, on the aft floor
        # side) gets the fingers that tie each channel into the bore.
        poly = bore_fingered if nm == "spacer_battery_1" else bore_plain
        b.cavity_placements.clear()
        b.cavity_placements.append(Placement(
            position_mm=(0.0, 0.0), rotation_deg=0.0, face="top",
            item=CavityRegion(name="cell_bores_merged", face="through",
                              exterior_polygon=poly, depth_mm=b.thickness_mm)))
        # Carry EVERY perimeter potting hole straight down as a through-channel.
        if b.geometry is not None:
            kept = [h for h in b.geometry.holes
                    if getattr(h, "tag", None) != "potting"]
            for xy in channels:
                kept.append(Hole(position_mm=xy, diameter_mm=_PHD,
                                 plated=False, tag="potting"))
            b.geometry.holes = kept


_PIEZO_DISC_R_MM = 5.0      # Ø10 Steminc SMD10T04R111 disc (SMD on fin_ble top)


# ── aft bench-array silkscreen groups ────────────────────────────────────
# Each functional run of pads gets a box on the BOTTOM silkscreen with its
# name above it. This is the legend a bench user reads before touching
# anything: which pads belong together, and — with the square pin-1 pad —
# which end a run starts at. Boxes are drawn AFTER _mark_spacer_cavity_silk
# (which clears every board's overlays before drawing the spacer-cut ghosts),
# so ordering of the two calls matters.
_AFT_SILK_GROUPS = [
    ("SPI",           ["TP_SPI_MOSI", "TP_SPI_CS_FIN", "TP_SPI_MISO", "TP_SPI_SCLK"]),
    ("FIN 1",         ["TP_FIN1_A1", "TP_FIN1_A2", "TP_FIN1_B1", "TP_FIN1_B2"]),
    ("FIN 3",         ["TP_FIN3_A1", "TP_FIN3_A2", "TP_FIN3_B1", "TP_FIN3_B2"]),
    ("FIN 2",         ["TP_FIN2_A1", "TP_FIN2_A2", "TP_FIN2_B1", "TP_FIN2_B2"]),
    ("FIN 4",         ["TP_FIN4_A1", "TP_FIN4_A2", "TP_FIN4_B1", "TP_FIN4_B2"]),
    ("CAN",           ["TP_CAN_N", "TP_CAN_P"]),
    ("BAT",           ["TP_BAT_RAW", "TP_BAT_PROT"]),
    ("ACTIVATE",      ["P_ACTIVATE_COMMON"]),
    ("GROUND",        ["TP_GND_ACT"]),
    ("ACTIVATION_UNLOCK", ["TP_ACT_CONFIRM", "TP_ACT_SET"]),
    ("HALL",          ["TP_FIN_HALL", "TP_HALL_VIN"]),
    ("I2C",           ["TP_I2C_SDA", "TP_I2C_SCL"]),
    ("JUMPSTART",     ["TP_JUMP_WAKE", "TP_JUMP_GND"]),
    ("PROGRAM_MP25",  ["TP_VDD", "TP_SWDIO", "TP_NRST", "TP_SWCLK",
                       "TP_MP25_GND1", "TP_SWO", "TP_MP25_GND2", "TP_BOOT0"]),
    ("GPIO",          ["TP_GPIO_0", "TP_GPIO_1", "TP_GPIO_2", "TP_GPIO_3"]),
]
_AFT_SILK_PAD_R_MM = 1.0     # Ø2.0 pad → 1.0 half-width
_AFT_SILK_MARGIN_MM = 0.15   # box clearance beyond the pad edge
                             # (kept tight: the caption for each row has
                             #  to fit in the gap to the row above)


def _mark_aft_bench_silk(boards: dict) -> None:
    """Box + label each bench-pad group on aft_end_board's BOTTOM silkscreen.

    Single-pad groups (activate, GROUND) get a label only — a box around one pad
    adds nothing and the copper is already unambiguous. Must run AFTER
    `_mark_spacer_cavity_silk`, which clears every board's silk_overlays."""
    b = boards.get("aft_end_board")
    if b is None:
        return
    at = {}
    for pl in getattr(b, "chip_placements", []):
        ref = getattr(getattr(pl, "item", None), "ref", None)
        if ref:
            at[ref] = pl.position_mm
    for label, refs in _AFT_SILK_GROUPS:
        pts = [at[r] for r in refs if r in at]
        if not pts:
            continue
        pad = _AFT_SILK_PAD_R_MM + _AFT_SILK_MARGIN_MM
        x0 = min(p[0] for p in pts) - pad
        x1 = max(p[0] for p in pts) + pad
        y0 = min(p[1] for p in pts) - pad
        y1 = max(p[1] for p in pts) + pad
        if len(pts) > 1:
            b.silk_overlays.append(
                ("B.SilkS",
                 [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                 label))
        else:
            # label-only: a degenerate span just above the lone pad
            b.silk_overlays.append(
                ("B.SilkS", [(x0, y1), (x1, y1)], label))


def _mark_spacer_cavity_silk(panel, boards: dict) -> None:
    """Draw each spacer's FINAL through-cut window onto the facing
    silkscreens of its two rigid neighbours, fold-mirrored into each
    neighbour's own frame: the next tile's B.SilkS (its bottom-face
    chips pocket into this spacer) and the prev tile's F.SilkS. A
    layout engineer can then move face chips on the tile and see the
    existing cutout boundary directly — staying inside it means the
    spacer needs no re-mill. Call LAST among the cavity passes (after
    the battery/radar cut post-processing) so the outline matches what
    the spacer actually ships with; re-runnable (clears its own
    overlays first)."""
    from smash.layout.cavities import fold_project
    from smash.state.geometry.cavity import CavityRegion
    chain = panel.snake_chain or []
    for b in boards.values():
        if getattr(b, "silk_overlays", None):
            b.silk_overlays.clear()
    for i, name in enumerate(chain):
        sp = boards.get(name)
        if sp is None or not getattr(sp, "is_spacer", False):
            continue
        regions = [pl.item for pl in sp.cavity_placements
                   if isinstance(pl.item, CavityRegion)
                   and pl.item.face == "through"]
        if not regions or name not in panel.tiles:
            continue
        sp_row = panel.tiles[name][1]
        for nbr_i, silk in ((i - 1, "F.SilkS"), (i + 1, "B.SilkS")):
            if not (0 <= nbr_i < len(chain)):
                continue
            nbr = boards.get(chain[nbr_i])
            if nbr is None or chain[nbr_i] not in panel.tiles:
                continue
            # RIGID neighbours only. A spacer's neighbour can itself be
            # a spacer (the battery column interleaves no boards) — but
            # spacers carry no movable chips, and the stack pose is
            # boards-upright/spacers-FLIPPED, so spacer↔spacer is
            # flip×flip = identity: the single fold-mirror below would
            # draw the neighbour's bore ROTATED onto a tile whose own
            # Edge.Cuts already shows the same cut (the ghost diamonds
            # the user caught on the battery spacers).
            if getattr(nbr, "is_spacer", False):
                continue
            same_row = panel.tiles[chain[nbr_i]][1] == sp_row
            for k, reg in enumerate(regions):
                pts = [fold_project(x, y, same_row)
                       for (x, y) in reg.exterior_polygon]
                nbr.silk_overlays.append(
                    (silk, pts, f"{name} cutout" if k == 0 else None))


def _mark_battery_chip_clearance(boards: dict, panel) -> None:
    """Clear the bracket-tile parts that poke into the end battery spacers —
    a TARGETED cut, not the placer's square-everything through-cut. BOTH
    battery modes: whatever rigid tile brackets the battery column gets its
    body-height parts pocketed. Triple: cell_floor's formed cell solder tabs
    (height_mm on the tab chips) aft; fin_ble's bottom face nose-ward (the
    ceiling since the 2026-07-31 reorder) — its flat + contact pads solder
    flush, and its body-height bottom parts (un-embedded passives tucked
    into the compartment) get hugging pockets via the generic path below.
    Single: aft_end is the aft bracket — its tab lands + activate-bank parts
    clear the same way.

    The piezo-DISC branch is a round special case (a thin disc at a locked
    centre → modelled as a round through-hole, a big drill not a square);
    since the reorder the disc rides fin_ble's TOP face and never brackets
    a battery spacer, so the branch is inert — kept for correctness if the
    disc ever returns to a bracket face. Everything else with body height
    gets hugging pockets unioned together. Flat pads solder flush and need
    no clearance, and there is NO milled potting channel (the column pots
    through the threaded holes), so neither the square nor the diagonal
    channel-band the placer emits belongs here. The lands clear this
    region by avoiding the placed components (the pocket-era keepouts are
    gone with the pocket — the SMD disc is just a placed part now).

    Call AFTER _mark_battery_pockets (which clears + re-stamps the bore).
    No-op without a panel (the projection needs the fold sense).

    SMASH_FEA_SIMPLE_BORE=1 skips the chip-clearance extras entirely
    (bore-only battery cavities): the full-stack FEA (tools/run_stack_fea.py)
    fragments the potted tower into a conformal monolith, and the healed
    clearance bumps — correct for fab — put small arc features on the
    coplanar spacer interfaces that intermittently break gmsh's boundary
    recovery (PLC/overlapping-facet errors, 2026-08-03/04, feature set
    varies with the run-to-run packing shuffle). The extras are ~1–2 mm²
    pockets with no structural role, so the FEA tower drops them; NEVER
    ship a STEP built with this flag."""
    import os as _os
    if _os.environ.get("SMASH_FEA_SIMPLE_BORE") == "1":
        return
    from shapely.geometry import box as _box, Point as _ShPt
    from shapely.ops import unary_union
    from smash.state.geometry.cavity import CavityRegion
    from smash.state.topology.placement import Placement
    from smash.layout.placer.grid import footprint_bbox_mm
    from smash.layout.cavities import fold_project, rotated_bbox_mm
    if panel is None:
        return
    chain = list(getattr(panel, "snake_chain", None) or [])
    tiles = panel.tiles or {}
    CLR = 0.3
    col_extras: list = []       # healed clearance extras, WHOLE column
    col_spacers: list = []      # every battery spacer, extras or not
    for i, nm in enumerate(chain):
        if not nm.startswith("spacer_battery"):
            continue
        sp = boards.get(nm)
        if sp is None:
            continue
        sp_row = tiles.get(nm, (None, None))[1]
        regions: list = []
        for nbr_name, face in (((chain[i - 1] if i > 0 else None), "top"),
                               ((chain[i + 1] if i + 1 < len(chain) else None),
                                "bottom")):
            nbr = boards.get(nbr_name) if nbr_name else None
            if nbr is None or getattr(nbr, "is_spacer", False):
                continue
            same_row = (tiles.get(nbr_name, (None, None))[1] == sp_row)
            for p in nbr.chip_placements:
                if getattr(p, "face", None) != face:
                    continue
                c = p.item
                if getattr(c, "manf_pn", None) == "LGA_lands":
                    continue
                fp = getattr(c, "footprint", None)
                # The round piezo disc — a thin disc, not a body-height chip, so
                # it's modelled by its real Ø10 footprint, centred (the fold of a
                # centred disc is the same disc).
                if getattr(c, "ref", "") == "P_PIEZO":
                    regions.append(_ShPt(0.0, 0.0).buffer(
                        _PIEZO_DISC_R_MM + CLR, quad_segs=24))
                    continue
                # Everything else: clear only parts with real body height (the
                # comparator ring); flat project pseudo-parts sit flush.
                h = (getattr(c, "height_mm", None)
                     or (getattr(fp, "height_mm", None) if fp else None))
                if fp is None or not h:
                    continue
                lo_x, lo_y, hi_x, hi_y = footprint_bbox_mm(fp)
                we, he = rotated_bbox_mm(hi_x - lo_x, hi_y - lo_y,
                                         getattr(p, "rotation_deg", 0) or 0)
                cx, cy = fold_project(p.position_mm[0], p.position_mm[1], same_row)
                regions.append(_box(cx - we / 2 - CLR, cy - he / 2 - CLR,
                                    cx + we / 2 + CLR, cy + he / 2 + CLR))
        # Heal each clearance against the spacer's existing cuts (the
        # bore stamped by _apply_battery_bore): the battery-facing faces
        # keep their parts INSIDE the bore circles (2026-07-31 rule), so
        # most chimneys are fully swallowed by the through-cut (drop
        # them), and a rim-hugging part's box can poke past the bore
        # 48-gon by a hair — unioned raw, that leaves a <0.3 mm sliver
        # bump that no mill can cut and that breaks the full-stack FEA's
        # fragment imprint ('overlapping facets'). Residuals thinner
        # than 2×CLR are inflated to a machinable ≥1.2 mm bump with
        # COARSE 45° arc facets (default polygonization + 3-dp rounding
        # emits 0.01–0.06 mm micro-chords → sliver tets → fake ~1.7 GPa
        # nodal peaks).
        from shapely.geometry import Polygon as _ShPoly2
        existing = []
        for pl in sp.cavity_placements:
            reg = getattr(pl, "item", None)
            if isinstance(reg, CavityRegion) and len(
                    reg.exterior_polygon) >= 3:
                existing.append(_ShPoly2(reg.exterior_polygon))
        bore_u = unary_union(existing) if existing else None
        if bore_u is not None:
            healed = []
            for reg in regions:
                resid = reg.difference(bore_u)
                if resid.is_empty:
                    continue                    # inside the bore — no cut needed
                # Margin-only graze: the part's BODY clears the through-cut and
                # only its +CLR safety ring laps the bore edge. No FR4 conflict
                # → no pocket (inflating these was the source of the scalloped
                # bump artifacts on every battery spacer, 2026-08-28).
                if reg.buffer(-CLR).difference(bore_u).is_empty:
                    continue
                if resid.buffer(-CLR).is_empty:
                    healed.append(resid.buffer(2 * CLR, join_style=1,
                                               quad_segs=2))
                else:
                    healed.append(reg)
            regions = healed
        col_extras.extend(regions)
        col_spacers.append(nm)

    # ── ONE SHARED cut for the whole column ──────────────────────────
    # Adjacent battery spacers are coplanar face-to-face in the potted
    # tower; if their cavity outlines differ by sub-0.05 mm anywhere,
    # the full-stack FEA's OCC fragment imprints two nearly-identical
    # loops onto the shared plane and emits degenerate self-intersecting
    # sliver curves (13 h gmsh grind / PLC errors, 2026-08-03/04). So
    # every spacer gets the IDENTICAL polygon: bore ∪ ALL clearance
    # extras of the column (battery_1 additionally keeps its potting
    # fingers — a big, clean feature that imprints fine). A mitre-close
    # (+0.2/−0.2, join_style=2 so straight bore chords round-trip
    # bit-exact) erases any remaining sub-0.4 mm FR4 sliver between a
    # bump and the bore. Cutting the extras through ALL spacers costs
    # ~1–2 mm² of ring each but also puts them inside the shared
    # `cell_bores_merged` union, so the column's LGA land pattern
    # (which subtracts exactly that union) can never park a land over a
    # clearance void.
    if not col_extras:
        return
    from shapely.geometry import Polygon as _ShPoly3
    extras_u = unary_union(col_extras)
    for nm in col_spacers:
        sp = boards[nm]
        existing = []
        for pl in sp.cavity_placements:
            reg = getattr(pl, "item", None)
            if (isinstance(reg, CavityRegion)
                    and len(reg.exterior_polygon) >= 3):
                existing.append(_ShPoly3(reg.exterior_polygon))
        merged = unary_union(existing + [extras_u])
        merged = (merged.buffer(0.2, join_style=2)
                  .buffer(-0.2, join_style=2))
        polys = (list(merged.geoms) if merged.geom_type == "MultiPolygon"
                 else [merged])
        sp.cavity_placements.clear()
        for j, poly in enumerate(polys):
            ring = [(round(x, 3), round(y, 3))
                    for x, y in poly.exterior.coords[:-1]]
            # Collapse sub-0.05 mm edges left by the union + 3-dp rounding
            # (an 8 µm chord survives the mitre-close on convex arcs) —
            # identical inputs → identical output on every spacer, so the
            # shared-outline contract holds.
            dedup = []
            for pt in ring:
                if (not dedup or (pt[0] - dedup[-1][0]) ** 2
                        + (pt[1] - dedup[-1][1]) ** 2 >= 0.05 ** 2):
                    dedup.append(pt)
            if len(dedup) >= 2 and ((dedup[0][0] - dedup[-1][0]) ** 2
                                    + (dedup[0][1] - dedup[-1][1]) ** 2
                                    < 0.05 ** 2):
                dedup.pop()
            sp.cavity_placements.append(Placement(
                position_mm=(0.0, 0.0), rotation_deg=0.0, face="top",
                item=CavityRegion(
                    name=("cell_bores_merged" if j == 0
                          else f"{nm}__bore_chip_clearance_{j}"),
                    face="through", exterior_polygon=dedup,
                    depth_mm=sp.thickness_mm)))




def _generate_config(name: str, board_set: set[str]) -> None:
    """Build, place, and export one board configuration to
    dist/<name>/ (per-board folders + <name>.kicad_pcb). Splits the
    board set into a fold-ordered snake + branch stubs (nfc/qpd/camera)."""
    _set_battery_mode(name)            # triple (default) or single (core_1cell)
    board_set = _config_boards(name, board_set)   # single drops cell_floor_board
    d = Design()
    _prime_power_rails(d)
    for bn in board_set:
        _BOARD_BUILDERS[bn](d)
    snake = [b for b in _MASTER_SNAKE if b in board_set]
    branches = [
        (_BRANCH_PARENT[leaf][0], leaf,
         Flex(length_mm=_BRANCH_PARENT[leaf][1],
              branch_side=_BRANCH_PARENT[leaf][2],
              s_fold=_BRANCH_PARENT[leaf][3]))
        for leaf in _BRANCH_PARENT
        if leaf in board_set and _BRANCH_PARENT[leaf][0] in board_set
    ]
    panel, boards = build_config_panel(snake, branches=branches,
                                       straight=_STRAIGHT_SNAKE,
                                       battery_length_mm=_compartment_mm())
    build_spacers(d, boards)
    _set_dynamic_spacer_thickness(d, boards)   # radar↔nose_cap = AWR − nose_cap
    _mark_preplace_keepouts(d, boards)         # AWR aperture + USB column (pre-place)
    # Economies of scale: shared chips lock to their maximalist positions,
    # so every config packs (and later mills/cuts) the identical board.
    ref = _MAX_REF or {}
    extra_locks: dict = {}
    for bn in board_set:
        extra_locks.update(ref.get("placements", {}).get(bn, {}))
    place_design(d, panel, boards, extra_locks=extra_locks or None)
    # Size each backbone spacer to the gap it bridges (placement-dependent, so
    # post-place); battery spacers keep their cell-length override.
    size_backbone_spacers(panel, boards)
    # After place_design — the placer clears every board's cavity_placements,
    # so the metal-block through-cut is appended here (not before).
    _mark_radar_block_cutout(boards)
    _mark_usb_cavity(boards)            # no-op; USB notch is in the board outline (_tile_cuts)
    _mark_battery_pockets(boards)
    _mark_battery_chip_clearance(boards, panel)   # round piezo + comparator clear
    # Backbone LGA interconnect — same post-processing as the maximalist panel,
    # so every shippable config carries the power/gnd/CAN lands through its
    # spacers (not just the maximalist build). Joints shared with the
    # maximalist build replay its patterns + nets verbatim (economies of
    # scale); truncated-away joints still fab their tile-face fields.
    _jref = dict(ref.get("joints") or {})
    if not _battery_column_conforms(panel, ref):
        # Moved/shrunk battery column (core_1cell): drop the battery joints
        # from the reference so the WHOLE column recomputes one consistent
        # pattern from its own bore (mixing replayed + fresh patterns
        # mid-column would break the pad-to-pad via stack).
        _jref = {k: v for k, v in _jref.items()
                 if not k.startswith("spacer_battery")}
    _lands = place_lga_lands(d, panel, boards,
                             connect=lambda net, pin: _net(d, net).connect(pin),
                             reference=_jref)
    _absent_fields = _replay_absent_joint_fields(
        d, panel, boards, {**ref, "joints": _jref})
    _replayed = [j for j in _lands
                 if j in _jref and _chain_neighbors(
                     list(panel.snake_chain), j)
                 == (_jref[j]["before"], _jref[j]["after"])]
    _launch = place_branch_flex_launches(
        d, boards, catalog=_FLEX_LAUNCH_CATALOG,
        connect=lambda net, pin: _net(d, net).connect(pin))
    if _launch:
        print("Branch-flex launch strips: "
              + ", ".join(f"{p_}→{c_}={n_}" for (p_, c_), n_ in _launch.items()))
    _drop_radar_nose_spacer(d, panel, boards)   # scaffold spacer → discard
    _apply_companion_reference_layout(d, boards)
    _apply_activation_reference_layout(d, boards)
    # Economies of scale: adjacency-conforming boards inherit the maximalist
    # cavities verbatim (they were milled from the same inherited chip
    # placements, but the maximalist copy is authoritative — panel-fold and
    # flex-chord clipping must not re-diverge them). Non-conforming boards
    # (novel adjacency, e.g. core_1cell's re-ordered battery column) keep
    # their own and are reported.
    _conform, _nonconform = _reference_conforming(panel, boards, ref)
    _cav_n = 0
    for bn in _conform:
        rc = (ref.get("cavities") or {}).get(bn)
        if rc is not None:
            boards[bn].cavity_placements[:] = list(rc)
            _cav_n += 1
    if _nonconform:
        print(f"  WARNING: {name}: non-conforming board(s) — NOT the shared "
              f"maximalist part: {', '.join(_nonconform)}", file=sys.stderr)
    _mark_spacer_cavity_silk(panel, boards)     # cutout windows → neighbour silk
    _mark_aft_bench_silk(boards)                # bench-pad group boxes + labels
    # Self-contained config folder at dist/<config>/: <config>.kicad_pcb
    # + per-board <tile>/ subfolders (3D models next to each tile).
    # Folded-tower stackup for this config stays at dist/ (see below).
    cfg_dir = _PCB_OUT / name
    cfg_dir.mkdir(parents=True, exist_ok=True)
    out = cfg_dir / f"{name}.kicad_pcb"
    r = write_kicad_panel(d, panel, boards, out)
    write_blank_drawing_sheet(out)
    # This config's spacers (cadquery). The snake adjacencies differ per
    # config — e.g. flight↔radar exists in core_radar but not the
    # maximalist panel — and a spacer's cavities are milled from its two
    # neighbours' chip faces in this fold, so each variant gets its own
    # spacer set under <config>/<spacer>/.
    # Per-board .kicad_pcb are ALWAYS written (cheap; the component stackup
    # assembly folds them) — _export_tile_steps skips its own STEP/STL when
    # SMASH_STEP_EXPORT=0. The heavy 3D bodies (cadquery spacers + stackup +
    # waveguide) stay gated so a fast netlist/panel run skips them.
    tiles_msg = _export_tile_steps(
        d, panel, boards, cfg_dir,
        cutouts_ref={bn: c for bn, c in (ref.get("cutouts") or {}).items()
                     if bn in _conform})
    if _STEP_ENABLED:
        sp = write_all_spacer_steps(boards, cfg_dir, subdir=True)
        if _STACKUP_ALL:
            _export_stackup(d, boards, panel.snake_chain,
                            _DIST / f"stackup_{name}.step",
                            tiles=panel.tiles)
            _export_components_stackup(boards, panel.snake_chain, cfg_dir,
                                       _DIST / f"stackup_{name}_components.step",
                                       tiles=panel.tiles)
            _export_print_stls(boards, panel.snake_chain, cfg_dir, cfg_dir)
        wg_msg = _export_waveguide_stubs(boards, cfg_dir / "waveguide_stubs.step")
        steps_msg = f"{len(sp)} spacers; {name}/ {tiles_msg}; {wg_msg}"
    else:
        steps_msg = f"{name}/ {tiles_msg}; 3D STEP skipped"

    # Per-reflow board-to-board assembly files (opt-in). Runs LAST so the
    # board-as-component chips it appends don't perturb the panel/tile writes
    # above; 3D models attach from this config's STEP dir when present.
    asm_msg = ""
    if _GEN_ASSEMBLIES:
        from smash.export.stack_assembly import build_stack_assembly_files
        res = build_stack_assembly_files(
            d, panel, boards, _ASSEMBLY_DIR / name,
            connect=lambda net, pin: _net(d, net).connect(pin),
            step_dir=(_PCB_OUT / name) if _STEP_ENABLED else None)
        asm_msg = f"; {len(res)} reflow files → assembly/{name}/"

    print(f"  {name}: {out.name} "
          f"({r['n_tiles']} tiles, {r['n_footprints']} footprints, "
          f"{r['n_flex_strips']} flex strips, "
          f"{sum(_lands.values())} LGA lands, "
          f"stack {panel.stack_height_mm(boards):.1f} mm; {steps_msg}{asm_msg})")
    print(f"    shared-part inheritance: {len(extra_locks)} placement locks, "
          f"{len(_replayed)}/{len(_lands)} joints replayed, "
          f"{_absent_fields} truncated-joint tile fields, "
          f"{_cav_n} boards' cavities inherited"
          + (f"; NON-CONFORMING: {len(_nonconform)}" if _nonconform else ""))


def main() -> int:
    d = Design()
    _set_battery_mode("maximalist")  # triple — the 3-cell default (flip 2026-07-28)

    _prime_power_rails(d)

    # Boards (ordered smallest → largest)
    build_qpd_module(d)
    build_yagi_antenna_a_flex(d)
    build_yagi_antenna_b_flex(d)
    build_nose_cap(d)
    build_camera_module(d)
    build_aft_end_board(d)
    if _BATTERY_MODE != "single":     # single drops cell_floor (cell on aft_end)
        build_cell_floor_board(d)
    build_activation_interface(d)
    build_radar_module_awr1843aop(d)
    build_companion_compute(d)
    # companion_io dropped: its parallel NAND moved to companion_compute as
    # two SPI-NAND dies; its G0B1+TCAN CAN node is retired with the tile.
    build_power_board(d)
    build_wakeup_board(d)   # also folds in the IMU/mag (build_flight_board, board_tag="wakeup_board")
    build_fins_module(d)    # fin actuators — on fin_ble_board (2026-07-30 crowding split off wakeup)

    # Build the panel first: the fold optimiser picks the snake order and
    # materialises one spacer Board per gap, so the spacer chips can only
    # be created once those Boards exist.
    panel, boards = build_panel(straight=_STRAIGHT_SNAKE,
                                single_cell=_BATTERY_MODE == "single",
                                battery_length_mm=_compartment_mm())
    build_spacers(d, boards)
    _set_dynamic_spacer_thickness(d, boards)   # radar↔nose_cap = AWR − nose_cap
    _mark_preplace_keepouts(d, boards)         # AWR aperture + USB column (pre-place)

    # ── place + export KiCad PCBs ────────────────────────────────────
    report = place_design(d, panel, boards)
    # Size each backbone spacer to the gap it bridges (placement-dependent, so
    # post-place); battery spacers keep their cell-length override.
    _sized = size_backbone_spacers(panel, boards)
    print(f"Backbone spacers sized to their gaps ({len(_sized)}): "
          + ", ".join(f"{v} mm" for v in _sized.values())
          + "  (was 4.0 mm fixed)")
    # After place_design — the placer clears every board's cavity_placements,
    # so the metal-block through-cut is appended here (not before).
    _mark_radar_block_cutout(boards)
    _mark_usb_cavity(boards)            # no-op; USB notch is in the board outline (_tile_cuts)
    _mark_battery_pockets(boards)
    _mark_battery_chip_clearance(boards, panel)   # round piezo + comparator clear

    if report.untagged_refs:
        print(f"WARN: {len(report.untagged_refs)} chips have no board_tag "
              f"(skipped): {report.untagged_refs[:5]}{'…' if len(report.untagged_refs) > 5 else ''}")
    if report.unknown_board_refs:
        print(f"WARN: {len(report.unknown_board_refs)} chips reference "
              f"unknown boards: {report.unknown_board_refs[:5]}")
    if report.any_overflow:
        bad = [s.board_name for s in report.per_board if s.overflow]
        print(f"WARN: {len(bad)} board(s) overflow: {bad}")

    # Geometric guard: a LOCKED placement overlapping anything is a hard
    # error (the placer can't move it); packed-vs-packed near-misses stay a
    # warning. assert_no_locked_overlaps raises on the former, returns the
    # latter.
    from smash.validators import assert_no_locked_overlaps
    overlaps = assert_no_locked_overlaps(boards)
    if overlaps:
        print(f"WARN: {len(overlaps)} packed chip-overlap(s):")
        for iss in overlaps[:10]:
            print(f"  {iss}")

    print(f"Placed {sum(s.n_packed + s.n_locked for s in report.per_board)} chips "
          f"across {sum(1 for s in report.per_board if s.n_packed + s.n_locked > 0)} "
          f"boards; {report.n_cavities_added} cavities attached to spacers.")

    # Board-to-board LGA interconnect — POST-PROCESSING after the placer:
    # adaptive square solder lands packed into the FREE area of each joint
    # (around components / cavities / potting holes), carrying the power/gnd/CAN
    # backbone through the FR4-spacer interposers (replaces the snake flexes).
    _joint_capture: dict = {}
    _lands = place_lga_lands(d, panel, boards,
                             connect=lambda net, pin: _net(d, net).connect(pin),
                             capture=_joint_capture,
                             pinned=_power_board_pinned_lands())
    _launch = place_branch_flex_launches(
        d, boards, catalog=_FLEX_LAUNCH_CATALOG,
        connect=lambda net, pin: _net(d, net).connect(pin))
    if _launch:
        print("Branch-flex launch strips: "
              + ", ".join(f"{p_}→{c_}={n_}" for (p_, c_), n_ in _launch.items()))
    _drop_radar_nose_spacer(d, panel, boards)   # scaffold spacer → discard
    _apply_companion_reference_layout(d, boards)
    _apply_activation_reference_layout(d, boards)
    _mark_spacer_cavity_silk(panel, boards)     # cutout windows → neighbour silk
    _mark_aft_bench_silk(boards)                # bench-pad group boxes + labels
    _lands.pop("spacer_radar_module_nose_cap", None)

    # ── capture the economies-of-scale reference for the config builds ──
    # Everything a config must fab IDENTICALLY comes from here: final chip
    # placements (post EE-layout), the LGA joint patterns + nets (the joint
    # capture above, scaffold radar↔nose joint included — its tile-face
    # lands survive the spacer drop), every board's milled cavities, and
    # each rigid tile's outline chords as cut in THIS panel.
    global _MAX_REF
    from types import SimpleNamespace as _NS
    from smash.export.kicad_pcb import (_cutouts_for_tile as _ref_cuts,
                                        _DEFAULT_FLEX_WIDTH_MM as _ref_fw)
    from smash.layout.placer.flex_sizing import compute_link_widths as _ref_clw
    _ref_lw, _ = _ref_clw(d, panel)
    _MAX_REF = {
        "joints": _joint_capture,
        "chain": list(panel.snake_chain),
        "placements": {
            bn: {pl.item.ref: _NS(position_mm=pl.position_mm,
                                  rotation_deg=pl.rotation_deg,
                                  face=pl.face)
                 for pl in b.chip_placements
                 if getattr(pl.item, "ref", None)
                 and getattr(pl.item, "manf_pn", None) != "LGA_lands"}
            for bn, b in boards.items()
            if not getattr(b, "is_spacer", False)},
        "cavities": {bn: list(b.cavity_placements)
                     for bn, b in boards.items()},
        "cutouts": {bn: _ref_cuts(bn, panel, _ref_fw, _ref_lw)
                    for bn, b in boards.items()
                    if not getattr(b, "is_spacer", False)
                    and getattr(b, "kind", "rigid") != "flex"
                    and b.geometry is not None},
    }
    print(f"Backbone LGA lands: {sum(_lands.values())} across "
          f"{len(_lands)} joints "
          f"({', '.join(f'{k}={v}' for k, v in _lands.items())})")

    # Geometric guard: no neighbour-tile chip may collide with a spacer's FR4
    # in the folded tower — each spacer cavity must clear the chips on the face
    # that points at it (fold-parity aware). Catches the class of bug where a
    # post-battery-compartment board folds inverted and the milled window lands
    # under the wrong face.
    from smash.validators import check_spacer_chip_clearance
    _clr = check_spacer_chip_clearance(panel, boards)
    if _clr:
        print(f"WARN: {len(_clr)} spacer↔chip collision(s) in the folded stack:")
        for _iss in _clr[:10]:
            print(f"  {_iss}")

    out = _DIST / "maximalist_canonical_netlist.json"
    summary = write_canonical_netlist(d, out)
    print(f"Canonical netlist written to {out.relative_to(REPO)} "
          f"({summary['n_parts']} parts, {summary['n_nets']} nets)")

    # Start dist/ clean of generated PCB/3D artifacts. Netlist above is
    # rewritten in place. Hand-edited .kicad_pcb files (stem ≠ directory
    # name and ≠ stackup) are salvaged to dist/kicad_pcbs_user/.
    pcb_out = _DIST
    keep_root = _DIST / "kicad_pcbs_user"

    def _salvage_stray_pcbs(root: pathlib.Path) -> None:
        if not root.exists():
            return
        for f in sorted(root.rglob("*.kicad_pcb")):
            try:
                rel = f.relative_to(root)
            except ValueError:
                continue
            if keep_root in f.parents or f.stem in (f.parent.name, "stackup", "smash_evb_panel"):
                continue
            dest = keep_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.replace(dest)
            print(f"preserved hand-edit: {f.relative_to(REPO)} → "
                  f"{dest.relative_to(REPO)}")

    _salvage_stray_pcbs(pcb_out / "kicad_pcbs_smash")
    _salvage_stray_pcbs(pcb_out)
    shutil.rmtree(pcb_out / "kicad_pcbs_smash", ignore_errors=True)
    shutil.rmtree(_MAXIMALIST_DIR, ignore_errors=True)
    shutil.rmtree(_ASSEMBLY_DIR, ignore_errors=True)
    for cfg_name in CONFIGS:
        shutil.rmtree(pcb_out / cfg_name, ignore_errors=True)
    for name in (
        "smash_evb_panel.kicad_pcb", "smash_evb_panel.kicad_pro",
        "smash_evb_panel.kicad_prl", "smash_evb_panel.kicad_wks",
        "stackup.kicad_pcb", "stackup.kicad_pro",
        "stackup.kicad_prl", "stackup.kicad_wks",
        "stackup.step", "stackup_no_potting.step", "stackup_components.step",
        "consolidated_stackup.stl", "housing.stl", "waveguide_stubs.step",
    ):
        (pcb_out / name).unlink(missing_ok=True)
    for extra in pcb_out.glob("stackup_*.step"):
        extra.unlink(missing_ok=True)
    pcb_out.mkdir(parents=True, exist_ok=True)

    # Panel-level file (primary output — every board + flex strips on
    # one canvas, opens directly in KiCad).
    panel_path = pcb_out / "stackup.kicad_pcb"
    r = write_kicad_panel(d, panel, boards, panel_path)
    write_blank_drawing_sheet(panel_path)
    print(f"KiCad panel written to {panel_path.relative_to(REPO)} "
          f"({r['n_tiles']} tiles, {r['n_footprints']} footprints, "
          f"{r['n_flex_strips']} flex strips, {r['n_holes']} holes, "
          f"{r['n_cavities']} cavity polygons, "
          f"stack {panel.stack_height_mm(boards):.1f} mm)")
    # Per-board .kicad_pcb are ALWAYS written (cheap; the component stackup
    # folds them) — _export_tile_steps skips its own STEP/STL when
    # SMASH_STEP_EXPORT=0. The heavier 3D bodies (kicad-cli tile STEPs +
    # cadquery 4 mm spacer bodies + folded-tower stackup for FEA) stay gated so
    # a fast netlist/panel run skips them. KiCad's panel STEP uses a uniform
    # 1.6 mm thickness (wrong for the rigid-flex spacers), hence cadquery.
    print(f"  tile PCBs: {_export_tile_steps(d, panel, boards, _MAXIMALIST_DIR)}")
    if _STEP_ENABLED:
        spacer_results = write_all_spacer_steps(boards, _MAXIMALIST_DIR, subdir=True)
        _sp_th = sorted({f"{r['thickness_mm']:.2f}" for r in spacer_results})
        print(f"Spacer STEPs written to {_MAXIMALIST_DIR.relative_to(REPO)}/ "
              f"({len(spacer_results)} files, FR4 interposers "
              f"{'/'.join(_sp_th)} mm + filled vias + routed cavities)")
        print(f"  {_export_stackup(d, boards, panel.snake_chain, pcb_out / 'stackup.step', tiles=panel.tiles)}")
        print(f"  {_export_components_stackup(boards, panel.snake_chain, _MAXIMALIST_DIR, pcb_out / 'stackup_components.step', tiles=panel.tiles)}")
        print(f"  {_export_print_stls(boards, panel.snake_chain, pcb_out, _MAXIMALIST_DIR)}")
        print(f"  {_export_waveguide_stubs(boards, pcb_out / 'waveguide_stubs.step')}")
    else:
        print("  3D STEP (spacers + stackup): SKIPPED (SMASH_STEP_EXPORT=0); per-board PCBs written")

    # ── board-configuration variants ────────────────────────────────
    # Each config re-places + re-exports a separate panel, so for fast
    # iteration limit what gets built:
    #   SMASH_SKIP_CONFIGS=1   → skip them all (just the maximalist panel)
    #   SMASH_CONFIGS=a,b,...  → build only those (default: all). Unknown names
    #                            error so a typo doesn't silently build nothing.
    if os.environ.get("SMASH_SKIP_CONFIGS", "0") == "1":
        print("Board configurations: SKIPPED (SMASH_SKIP_CONFIGS=1)")
    else:
        sel = os.environ.get("SMASH_CONFIGS", "").strip()
        if sel:
            want = [s.strip() for s in sel.split(",") if s.strip()]
            unknown = [w for w in want if w not in CONFIGS]
            if unknown:
                raise SystemExit(
                    f"SMASH_CONFIGS: unknown config(s) {unknown}; "
                    f"valid: {sorted(CONFIGS)}")
            chosen = {w: CONFIGS[w] for w in want}
        else:
            chosen = dict(CONFIGS)
        print(f"Board configurations ({len(chosen)}/{len(CONFIGS)}"
              + (f": {', '.join(chosen)}" if sel else "") + "):")
        for cfg_name, cfg_boards in chosen.items():
            _generate_config(cfg_name, cfg_boards)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
